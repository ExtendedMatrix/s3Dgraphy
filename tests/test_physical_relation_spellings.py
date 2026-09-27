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
* the datamodel must declare exactly one member canonical, and it does so as
  DATA: every other member carries `spelling_of: <canonical>` (connections
  datamodel 1.6.20, 2026-09-27) — same relation, same RDF projection, accepted
  when read, never written. Not `deprecated`, which drops the edge from RDF
  (measured). The «Canonical…» in the description stays, as an explanation for
  a human, and is no longer read here;
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
    # the RAW entries, as the JSON has them: `spelling_of` is read from the
    # source, not from the loader's view of it (the loader is tested apart)
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
    """The members that are NOT a spelling of another — read off the field."""
    return {n for n in names if not _edge_types()[n].get("spelling_of")}


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
        (canonical,) = chosen
        for name in names - chosen:
            assert _edge_types()[name]["spelling_of"] == canonical, name
        for name in names:
            assert _edge_types()[name].get("reverse") is None, \
                f"{name}: a spelling pair is only harmless when symmetric"


def test_spelling_of_is_declared_only_inside_a_pair():
    """The field and the derivation agree the other way round too: no entry
    outside the pairs claims to be a spelling (a stray `spelling_of` would make
    `normalize_edge_name` rename an edge that projects elsewhere)."""
    in_pairs = set().union(*_spelling_groups().values())
    declared = {n for n, e in _edge_types().items() if e.get("spelling_of")}
    assert declared and declared <= in_pairs, declared - in_pairs


def test_the_loader_exposes_the_field():
    """What every reader and writer in the code asks — the one door."""
    dm = get_connections_datamodel()
    canonical, aliases = _canonical_and_aliases()
    for name in aliases:
        target = _edge_types()[name]["spelling_of"]
        assert dm.normalize_edge_name(name) == target
        assert dm.normalize_edge_name(name, prefer_canonical=False) == target
        assert dm.is_canonical(name) is False
        assert dm.get_edge_definition(name)["canonical_name"] == target
        assert dm.spellings(name) == dm.spellings(target) >= {name, target}
    for name in canonical:
        assert dm.normalize_edge_name(name) == name and dm.is_canonical(name)
    # a reverse is NOT a spelling: it swaps the ends
    assert dm.spellings("overlies") == {"overlies"}


def test_the_rdf_reader_picks_the_same_canonical_as_the_datamodel():
    from s3dgraphy.importer.rdf_importer import _InverseDatamodel

    inv = _InverseDatamodel()
    for names in _spelling_groups().values():
        assert {inv.symmetric_spellings(sorted(names))} == \
            _declared_canonical(names), names


# ── the code writes the canonical spelling ──────────────────────────────────

#: Writers that still put the LEGACY spelling into a graph. Each is a place
#: where the choice of spelling is made in code or config; the list may only
#: shrink.
#:
#: 2026-10-18: two. 2026-09-27 (una grafia sola): `sync/rapporti.py:
#: parse_rapporti` REPAIRED — it writes `bonded_to` / `equals` in all ten
#: languages. 2026-10-20 (MICRO, decided by E.D. on 2026-09-27):
#: `mappings/generic/excel_to_graphml_mapping.json` REPAIRED — its `BONDED_TO`
#: and `EQUALS` columns now declare `edge_type: bonded_to` / `equals`, so the
#: generic importer writes the canonical name without `canonicalize_reverse`
#: (which stays opt-in, untouched). None left: the set may only stay empty.
KNOWN_LEGACY_WRITERS: set = set()


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


def test_a_malformed_spelling_of_is_refused_at_load(tmp_path):
    """A `spelling_of` naming nothing, another spelling, or a relation with a
    direction would send `normalize_edge_name` somewhere else in silence — so
    the loader refuses the file rather than tolerating it."""
    import pytest
    from s3dgraphy.edges.connections_loader import ConnectionsDatamodel

    source = PKG / "JSON_config" / "s3Dgraphy_connections_datamodel.json"
    for bad in ("no_such_edge", "is_physically_equal_to", "overlies"):
        data = json.loads(source.read_text(encoding="utf-8"))
        data["edge_types"]["is_bonded_to"]["spelling_of"] = bad
        path = tmp_path / f"{bad}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="spelling_of"):
            ConnectionsDatamodel(str(path))
