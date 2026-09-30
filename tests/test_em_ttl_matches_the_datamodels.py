"""`em.ttl` against the datamodels, whole — not one alignment at a time.

Until 2026-10-01 only single alignments had tests
(`test_em_ttl_names_the_same_edges_the_datamodel_maps`,
`test_em_ttl_declares_the_companion_subproperty`, …) and the count «every `em:`
term a datamodel cites is declared» was a measure made by hand
(docs/SOURCE_OF_TRUTH.md). This compares the two sets:

* **cited** — every value in the datamodel JSONs that IS an `em:` term (the
  whole string `em:Foo`, or the full IRI): a class's `uri`, an edge's
  `extension_mapping`, a `subclass_of`, an `rdf` block's
  `specialised_alternative`, … Prose (descriptions, changelogs, notes) is not
  read: a description that mentions `em:bonded_to` as history cites nothing;
* **declared** — every subject in the `em:` namespace in `em.ttl`.

A cited term that `em.ttl` does not declare makes a triple no reasoner knows:
that direction holds today and fails hard.

A declared term that no datamodel cites is the other direction, and TODAY IT
DOES NOT HOLD: 35 terms are emitted by code (the RDF exporter's `type_tag` →
subproperty table, the stamps, the AI support fields, the geometry fields)
without the datamodel naming them. The test is marked as expected to fail, with
the list, and `em.ttl` is NOT corrected by hand here: whether each term belongs
in a datamodel field or the exporter's table is a decision per term. A second
test pins the list, so the set cannot grow — or shrink — without somebody
editing it on purpose.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy.datamodel import DATAMODEL_FILES, JSON_CONFIG   # noqa: E402

rdflib = pytest.importorskip("rdflib")

EM = "https://w3id.org/em/ontology#"
_CURIE = re.compile(r"^em:([A-Za-z_]\w*)$")

#: Declared in em.ttl, cited by no datamodel JSON (measured 2026-10-01, em.ttl
#: 1.6.9, nodes 1.6.17, connections 1.6.31). Grouped by who emits them today.
KNOWN_UNCITED = {
    # physical-relation subproperties: the exporter maps mapping.type_tag to them
    # (rdf_exporter.py, the AP11 table); the edge entry names only AP11
    "abuts", "cuts", "fills", "overlies", "bondedTo", "physicallyEquals",
    # editorial stamps and tombstones (editorial.py, crdt)
    "createdBy", "lastEditedBy", "modifiedAt", "removedAt", "removedBy",
    # AI support and verification on nodes (ai_validation.py)
    "aiAssistedBy", "aiAssistedField", "aiModel", "aiPromptRef", "validatedAt",
    "modelIdentifier", "promptReference", "confidenceLevel", "orcidVerified",
    # geometry and place
    "convexShape", "sphere", "crs", "LocalSceneFrame",
    # the rest
    "checksum", "derivedFromDocument", "hasQualiaType", "hypothesizedBy",
    "inheritsQualia", "propagation", "reconstructsAbsent", "reconstructsFrom",
    "residency", "resourceScope", "wasReusedFrom",
}


def _declared() -> set:
    g = rdflib.Graph()
    g.parse(str(JSON_CONFIG / "em.ttl"), format="turtle")
    return {str(s)[len(EM):] for s in g.subjects() if str(s).startswith(EM)}


def _cited() -> dict:
    """term -> {"file:key", …} for every value that IS an em: term."""
    found: dict = {}

    def walk(value, key, filename):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k, filename)
        elif isinstance(value, list):
            for v in value:
                walk(v, key, filename)
        elif isinstance(value, str):
            m = _CURIE.match(value.strip())
            term = m.group(1) if m else (value[len(EM):] if value.startswith(EM) else None)
            if term:
                found.setdefault(term, set()).add(f"{filename}:{key}")

    for filename, _ in DATAMODEL_FILES.values():
        doc = json.loads((JSON_CONFIG / filename).read_text(encoding="utf-8"))
        walk(doc, "", filename)
    return found


def test_the_datamodels_cite_terms_at_all():
    # a guard for the reader below: if it read nothing, both tests would be empty
    assert len(_cited()) > 50


def test_every_em_term_a_datamodel_cites_is_declared_in_em_ttl():
    declared = _declared()
    missing = {t: sorted(w) for t, w in _cited().items() if t not in declared}
    assert not missing, f"cited by a datamodel, not declared in em.ttl: {missing}"


@pytest.mark.xfail(strict=True, reason=(
    "35 em: terms are declared in em.ttl and emitted by code, cited by no datamodel "
    "JSON (see KNOWN_UNCITED); a decision per term, not a hand fix of em.ttl"))
def test_every_em_term_declared_in_em_ttl_is_cited_by_a_datamodel():
    extra = sorted(_declared() - set(_cited()))
    assert not extra, f"declared in em.ttl, cited by no datamodel: {extra}"


def test_the_uncited_terms_are_exactly_the_known_ones():
    extra = _declared() - set(_cited())
    assert extra - KNOWN_UNCITED == set(), (
        f"NEW terms in em.ttl that no datamodel cites: {sorted(extra - KNOWN_UNCITED)}")
    assert KNOWN_UNCITED - extra == set(), (
        f"these are now cited (or gone): take them off KNOWN_UNCITED: "
        f"{sorted(KNOWN_UNCITED - extra)}")
