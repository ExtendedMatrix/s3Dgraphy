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

A declared term that no datamodel cites is the other direction. Until
2026-10-01 it did not hold: 35 terms were emitted by code (the RDF exporter's
`type_tag` → subproperty table, the stamps, the AI support fields, the geometry
fields) without the datamodel naming them. E.D. decided that day that the
datamodel JSON is the truth: 30 are now cited (node datamodel 1.6.18,
connections 1.6.32, qualia 1.6.3), and the rest are EXCEPTIONS, each with its
reason written in `EM_TTL_EXCEPTIONS`. The test is hard both ways: a term
neither cited nor excepted fails, an exception without a reason fails, and an
exception that has become cited (or left em.ttl) fails until it is taken off.
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

#: Declared in em.ttl and cited by no datamodel, ON PURPOSE: term -> the reason.
#: Measured 2026-10-26 (em.ttl 1.6.9, nodes 1.6.18, connections 1.6.32): the five
#: terms of the EM theory of virtual, documentary, reassembled and reused units
#: that no code writes and no edge of the graph carries. Three since connections
#: 1.6.33 (MICRO la lingua dei dati, part H, decided by E.D. 2026-10-01):
#: em:derivedFromDocument leaves with has_documentation from a USD
#: (extension_when.source_node_class) and em:reconstructsFrom with is_part_of
#: SF -> VSF, read from the whole (inverse_extension), so both are cited there.
_NO_EDGE = ("a term of the ontology without an edge in the graph; "
            "it is added when one is needed")
EM_TTL_EXCEPTIONS = {
    # VirtualSU -> crminf:I1_Argumentation. A virtual unit reaches its reasoning
    # through has_paradata_nodegroup (a ParadataNodeGroup, E89, not an I1) or
    # through its properties' has_data_provenance: no edge unit -> argumentation.
    "hypothesizedBy": _NO_EDGE,
    # VirtualSU -> the absent A8 it stands for. The absent unit is not a node:
    # no edge between two stratigraphic nodes means "reconstructs".
    "reconstructsAbsent": _NO_EDGE,
    # ReusedSpecialFind -> the ORIGINAL context. is_part_of from an RSF names the
    # host it is in now, not the one it was taken from.
    "wasReusedFrom": _NO_EDGE + (
        " (is_part_of from an RSF is the host it sits in now, not the context "
        "it was taken from)"),
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


def test_every_em_term_declared_in_em_ttl_is_cited_or_an_exception():
    extra = sorted(_declared() - set(_cited()) - set(EM_TTL_EXCEPTIONS))
    assert not extra, (
        f"declared in em.ttl, cited by no datamodel and not an exception: {extra}")


def test_every_exception_has_its_reason():
    blank = sorted(t for t, why in EM_TTL_EXCEPTIONS.items()
                   if not isinstance(why, str) or not why.strip())
    assert not blank, f"an exception without a reason: {blank}"


def test_the_exceptions_are_still_exceptions():
    declared, cited = _declared(), set(_cited())
    gone = sorted(set(EM_TTL_EXCEPTIONS) - declared)
    assert not gone, f"no longer declared in em.ttl: take them off EM_TTL_EXCEPTIONS: {gone}"
    now_cited = sorted(set(EM_TTL_EXCEPTIONS) & cited)
    assert not now_cited, (
        f"now cited by a datamodel: take them off EM_TTL_EXCEPTIONS: {now_cited}")


def test_the_ap11_table_is_read_from_the_datamodel():
    """The exporter's type_tag -> subproperty table is the datamodel's, and it
    is the one the exporter held by hand until connections 1.6.31."""
    from s3dgraphy.exporter.rdf_exporter import AP11_SUBPROPS, ap11_subprops
    conn = json.loads((JSON_CONFIG / DATAMODEL_FILES["connections"][0])
                      .read_text(encoding="utf-8"))
    assert AP11_SUBPROPS == ap11_subprops(conn)
    assert {tag: str(iri)[len(EM):] for tag, iri in AP11_SUBPROPS.items()} == {
        "abuts": "abuts", "cuts": "cuts", "fills": "fills", "overlies": "overlies",
        "bonded to": "bondedTo", "is bonded to": "bondedTo",
        "equals": "physicallyEquals"}
    for name, entry in conn["edge_types"].items():
        mapping = entry.get("mapping") or {}
        if mapping.get("type_tag"):
            assert mapping.get("subproperty", "").startswith("em:"), name
