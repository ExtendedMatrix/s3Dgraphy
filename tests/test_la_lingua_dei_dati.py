"""La lingua dei dati — tag di lingua sui testi, nomi invarianti (E.D., 2026-09-28).

Every guard is shown on a case that makes it fire:

* the datamodel MARKS what is natural language (Node.properties.description,
  the quale narrative_content) and nothing else — not name, not
  inventory_number, though both are strings;
* the cascade: the node's data.lang → the study's working language → none;
* never declared = untagged and counted; declared unknown = @und, not counted;
* an invalid tag is refused where it would be written, and nothing is written;
* em.json → TTL → em.json gives back data.lang exactly where it was.

And part H (decided by E.D. 2026-10-01): em:derivedFromDocument from a USD's
has_documentation, em:reconstructsFrom from a VSF to the SF that is part of it.
"""

from __future__ import annotations

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal, Namespace, URIRef  # noqa: E402
from rdflib.namespace import DCTERMS, RDFS  # noqa: E402

from s3dgraphy import api  # noqa: E402
from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter, _Datamodel  # noqa: E402
from s3dgraphy.graph import Graph  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402
from s3dgraphy.language import (check_language_tag, is_language_tag,  # noqa: E402
                                working_language)
from s3dgraphy.nodes.document_node import DocumentNode  # noqa: E402
from s3dgraphy.nodes.property_node import PropertyNode  # noqa: E402
from s3dgraphy.nodes.stratigraphic_node import (  # noqa: E402
    DocumentaryStratigraphicUnit, SpecialFindUnit, StratigraphicUnit,
    VirtualSpecialFindUnit)

CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
EM = Namespace("https://w3id.org/em/ontology#")


def _export(graph, tmp_path, name="g.ttl"):
    exporter = RDFExporter(str(tmp_path / name), format="turtle")
    path = exporter.export_single_graph(graph)
    store = rdflib.ConjunctiveGraph()
    store.parse(path, format="turtle")
    return exporter, store, path


def _iri(exporter, graph, node_id):
    return exporter._node_iri(graph.graph_id, node_id)


def _one(store, s, p):
    values = list(store.objects(s, p))
    assert len(values) == 1, values
    return values[0]


def _unit_graph(study_lang=None, **node_data):
    g = Graph("lingua")
    us = StratigraphicUnit("us1", "USM5023", "muro in opera laterizia")
    if node_data:
        us.data = dict(node_data)
    g.add_node(us)
    if study_lang:
        api.set_working_language(g, study_lang)
    return g


# ── the datamodel says what is text ──────────────────────────────────────────

def test_the_marker_is_on_description_and_inherited_never_on_name():
    dm = _Datamodel()
    for cls in (StratigraphicUnit, DocumentNode, PropertyNode, SpecialFindUnit):
        assert dm.is_natural_language(cls, "description"), cls.__name__
        assert not dm.is_natural_language(cls, "name"), cls.__name__


def test_the_quale_marker_tells_prose_from_a_code():
    dm = _Datamodel()
    prose = PropertyNode("p1", "narrative_content", value="la guerra di Troia",
                         property_type="narrative_content")
    code = PropertyNode("p2", "inventory_number", value="MNR 12345",
                        property_type="inventory_number")
    assert dm.is_natural_language(prose, "value")
    assert not dm.is_natural_language(code, "value")


# ── the cascade ──────────────────────────────────────────────────────────────

def test_study_it_tags_the_description_and_leaves_the_name_alone(tmp_path):
    g = _unit_graph(study_lang="it")
    exporter, store, _ = _export(g, tmp_path)
    us = _iri(exporter, g, "us1")
    desc = _one(store, us, DCTERMS.description)
    assert desc == Literal("muro in opera laterizia", lang="it")
    label = _one(store, us, RDFS.label)
    assert label.language is None and str(label) == "USM5023"
    assert exporter.stats["literals_tagged_study"] == 1
    assert exporter.stats["literals_untagged"] == 0
    # the study's language is declared on the graph
    assert _one(store, exporter._graph_iri(g), DCTERMS.language) == Literal("it")


def test_the_node_language_wins_over_the_study(tmp_path):
    g = _unit_graph(study_lang="it", lang="ro")
    exporter, store, _ = _export(g, tmp_path)
    desc = _one(store, _iri(exporter, g, "us1"), DCTERMS.description)
    assert desc.language == "ro"
    assert exporter.stats["literals_tagged_node"] == 1
    assert exporter.stats["literals_tagged_study"] == 0


def test_no_language_anywhere_is_untagged_and_counted(tmp_path):
    g = _unit_graph()
    exporter, store, _ = _export(g, tmp_path)
    desc = _one(store, _iri(exporter, g, "us1"), DCTERMS.description)
    assert desc.language is None
    assert exporter.stats["literals_untagged"] == 1
    assert (exporter._graph_iri(g), DCTERMS.language, None) not in store
    assert "1 untagged" in exporter.summary()


def test_und_is_a_declaration_not_a_silence(tmp_path):
    g = _unit_graph(lang="und")
    exporter, store, _ = _export(g, tmp_path)
    desc = _one(store, _iri(exporter, g, "us1"), DCTERMS.description)
    assert desc.language == "und"
    assert exporter.stats["literals_untagged"] == 0
    assert exporter.stats["literals_tagged_node"] == 1


def test_qualia_prose_is_tagged_a_code_never(tmp_path):
    g = Graph("qualia")
    g.add_node(PropertyNode("p1", "narrative_content", value="la guerra di Troia",
                            property_type="narrative_content"))
    g.add_node(PropertyNode("p2", "inventory_number", value="MNR 12345",
                            property_type="inventory_number"))
    api.set_working_language(g, "it")
    exporter, store, _ = _export(g, tmp_path)
    prose = _one(store, _iri(exporter, g, "p1"), CRM.P90_has_value)
    code = _one(store, _iri(exporter, g, "p2"), CRM.P90_has_value)
    assert prose == Literal("la guerra di Troia", lang="it")
    assert code.language is None and str(code) == "MNR 12345"


def test_the_graph_description_takes_the_study_language_its_name_does_not(tmp_path):
    g = _unit_graph(study_lang="he")
    g.name = "Tel Dor"
    g.description = "חפירה"
    exporter, store, _ = _export(g, tmp_path)
    graph_iri = exporter._graph_iri(g)
    assert _one(store, graph_iri, DCTERMS.description).language == "he"
    assert _one(store, graph_iri, RDFS.label).language is None


def test_the_narrative_keeps_p72_and_its_text_takes_the_tag(tmp_path):
    from s3dgraphy.nodes.narrative_node import NarrativeNode
    g = Graph("narr")
    n = NarrativeNode("n1", "Racconto", lang="it")
    n.description = "il racconto dello scavo"
    g.add_node(n)
    exporter, store, _ = _export(g, tmp_path)
    iri = _iri(exporter, g, "n1")
    assert _one(store, iri, CRM.P72_has_language) == Literal("it")
    assert _one(store, iri, DCTERMS.description).language == "it"


# ── an invalid tag is not written ────────────────────────────────────────────

@pytest.mark.parametrize("tag", ["it", "ro", "he", "en-GB", "sr-Latn", "es-419", "und"])
def test_bcp47_tags_are_accepted(tag):
    assert is_language_tag(tag)
    assert check_language_tag(f" {tag} ") == tag


@pytest.mark.parametrize("tag", ["italiano", "it_IT", "", "e", "en-", 7, None])
def test_what_is_not_a_tag_is_refused(tag):
    assert not is_language_tag(tag)
    with pytest.raises(ValueError, match="not a language tag"):
        check_language_tag(tag)


def test_an_invalid_study_language_is_refused_and_nothing_written():
    g = _unit_graph()
    with pytest.raises(ValueError, match="'italiano' is not a language tag"):
        api.set_working_language(g, "italiano")
    assert working_language(g) is None
    assert not g.get_nodes_by_type("graph"), "no graph-self node made for nothing"


def test_an_invalid_node_language_is_refused_by_set_field():
    g = _unit_graph()
    us = g.find_node_by_id("us1")
    with pytest.raises(ValueError, match="not a language tag"):
        api.set_field(us, "data.lang", "italiano", author="0000-0002-1825-0097")
    assert "lang" not in (getattr(us, "data", None) or {})
    api.set_field(us, "data.lang", "it", author="0000-0002-1825-0097")
    assert us.data["lang"] == "it"


def test_an_invalid_node_language_is_refused_by_the_operations():
    section = {"nodes": [], "edges": []}
    bad = api.make_op("add_node", id="us9", node={
        "id": "us9", "node_type": "US", "name": "US 9",
        "data": {"lang": "italiano"}}, ts="2026-10-01T10:00:00Z", author="a")
    result = api.apply_op(section, bad)
    assert not result["applied"] and "not a language tag" in result["reason"]
    assert section["nodes"] == []

    good = api.make_op("add_node", id="us9", node={
        "id": "us9", "node_type": "US", "name": "US 9",
        "data": {"lang": "he"}}, ts="2026-10-01T10:00:00Z", author="a")
    assert api.apply_op(section, good)["applied"]
    upd = api.make_op("update_field", node_id="us9", field="data.lang",
                      value="ebraico", ts="2026-10-01T10:01:00Z", author="a")
    result = api.apply_op(section, upd)
    assert not result["applied"] and "not a language tag" in result["reason"]
    assert section["nodes"][0]["data"]["lang"] == "he"


# ── the study card ───────────────────────────────────────────────────────────

def test_the_study_card_carries_the_working_language():
    g = _unit_graph(study_lang="ro")
    card = api.study_metadata(api.container_of(g))
    assert card["language"] == "ro"
    assert api.study_metadata(api.container_of(_unit_graph()))["language"] is None


def test_the_legacy_graph_data_spelling_is_read_as_a_fallback():
    g = _unit_graph()
    g.data["language"] = "it"
    assert working_language(g) == "it"


# ── the round trip ───────────────────────────────────────────────────────────

def _langs(graph):
    return {n.node_id: (n.data or {}).get("lang") for n in graph.nodes
            if isinstance(getattr(n, "data", None), dict) and "lang" in n.data}


def test_emjson_ttl_emjson_keeps_data_lang_only_where_it_was(tmp_path):
    g = Graph("giro")
    g.add_node(StratigraphicUnit("us1", "US 3014", "strato di crollo"))
    ro = StratigraphicUnit("us2", "US 3015", "strat de dărâmături")
    ro.data = {"lang": "ro"}
    g.add_node(ro)
    und = StratigraphicUnit("us3", "US 3016", "?")
    und.data = {"lang": "und"}
    g.add_node(und)
    api.set_working_language(g, "it")

    graph, _warnings = parse_emjson(build_emjson(g))
    before = _langs(graph)
    assert before == {"us2": "ro", "us3": "und"}

    _exporter, _store, path = _export(graph, tmp_path)
    back = RDFImporter().parse(path)[0]
    assert _langs(back) == before
    assert working_language(back) == "it"

    # and once more through em.json: the same
    again, _ = parse_emjson(build_emjson(back))
    assert _langs(again) == before and working_language(again) == "it"


def test_a_node_language_equal_to_the_study_comes_back_identical(tmp_path):
    """D.1, closed by le traduzioni (2b): a data.lang equal to the study's is the
    node's own declaration and comes back as it was — em:originalLanguage says
    it, whatever the study says. Until then it was a declared limit."""
    g = _unit_graph(study_lang="it", lang="it")
    exporter, store, path = _export(g, tmp_path)
    assert _one(store, _iri(exporter, g, "us1"), EM.originalLanguage) == Literal("it")
    back = RDFImporter().parse(path)[0]
    us = back.find_node_by_id("us1")
    assert us.data.get("lang") == "it"
    assert working_language(back) == "it"


def test_original_language_is_written_only_where_declared(tmp_path):
    g = _unit_graph(study_lang="it")
    exporter, store, path = _export(g, tmp_path)
    assert (_iri(exporter, g, "us1"), EM.originalLanguage, None) not in store
    back = RDFImporter().parse(path)[0]
    assert "lang" not in (getattr(back.find_node_by_id("us1"), "data", None) or {})


def test_untagged_literals_still_read(tmp_path):
    g = _unit_graph()
    _exporter, _store, path = _export(g, tmp_path)
    back = RDFImporter().parse(path)[0]
    us = back.find_node_by_id("us1")
    assert us.description == "muro in opera laterizia"
    assert "lang" not in (getattr(us, "data", None) or {})


# ── part H: two em.ttl terms from edges that were already there ──────────────

def _documented(unit):
    g = Graph("doc")
    g.add_node(unit)
    g.add_node(DocumentNode("d1", "D.1", "pianta del 1890"))
    g.add_edge("e1", unit.node_id, "d1", "has_documentation")
    return g


def test_a_usd_is_derived_from_its_document(tmp_path):
    g = _documented(DocumentaryStratigraphicUnit("usd1", "USD 1", ""))
    exporter, store, _ = _export(g, tmp_path)
    usd, doc = _iri(exporter, g, "usd1"), _iri(exporter, g, "d1")
    assert (usd, CRM.P70i_is_documented_in, doc) in store
    assert (usd, EM.derivedFromDocument, doc) in store


def test_a_us_is_only_documented(tmp_path):
    g = _documented(StratigraphicUnit("us1", "US 1", ""))
    exporter, store, _ = _export(g, tmp_path)
    us, doc = _iri(exporter, g, "us1"), _iri(exporter, g, "d1")
    assert (us, CRM.P70i_is_documented_in, doc) in store
    assert (None, EM.derivedFromDocument, None) not in store


def _reassembled():
    g = Graph("vsf")
    g.add_node(SpecialFindUnit("sf1", "SF 1", ""))
    g.add_node(VirtualSpecialFindUnit("vsf1", "VSF 1", ""))
    g.add_node(StratigraphicUnit("us1", "US 1", ""))
    g.add_edge("e1", "sf1", "vsf1", "is_part_of")
    g.add_node(SpecialFindUnit("sf2", "SF 2", ""))
    g.add_edge("e2", "sf2", "us1", "is_part_of")
    return g


def test_a_vsf_is_reconstructed_from_the_sf_part_of_it(tmp_path):
    g = _reassembled()
    exporter, store, _ = _export(g, tmp_path)
    sf, vsf = _iri(exporter, g, "sf1"), _iri(exporter, g, "vsf1")
    assert (sf, CRM.P46i_forms_part_of, vsf) in store
    assert (vsf, EM.reconstructsFrom, sf) in store
    # a SF inside a US is containment and nothing more
    assert len(list(store.triples((None, EM.reconstructsFrom, None)))) == 1


def test_a_reverse_drawn_has_part_still_reconstructs(tmp_path):
    g = Graph("vsf_rev")
    g.add_node(SpecialFindUnit("sf1", "SF 1", ""))
    g.add_node(VirtualSpecialFindUnit("vsf1", "VSF 1", ""))
    g.add_edge("e1", "vsf1", "sf1", "has_part")
    exporter, store, _ = _export(g, tmp_path)
    sf, vsf = _iri(exporter, g, "sf1"), _iri(exporter, g, "vsf1")
    assert (vsf, EM.reconstructsFrom, sf) in store


@pytest.mark.parametrize("build", [
    lambda: _documented(DocumentaryStratigraphicUnit("usd1", "USD 1", "")),
    _reassembled,
])
def test_part_h_round_trips_without_extra_edges(tmp_path, build):
    from rdflib.compare import isomorphic
    g = build()
    importer = RDFImporter()
    _e, store1, path = _export(g, tmp_path, "a.ttl")
    back = importer.parse(path)[0]
    edges = lambda gr: sorted((e.edge_source, e.edge_type, e.edge_target)  # noqa: E731
                              for e in gr.edges)
    assert edges(back) == edges(g), importer.warnings
    assert not [w for w in importer.warnings if "matches no edge type" in w]
    _e, store2, _ = _export(back, tmp_path, "b.ttl")
    assert isomorphic(store1, store2)


# ── the doubtful qualia, measured (le traduzioni, part C; E.D. 2026-10-01) ────

_PROSE_QUALIA = {
    "intervention_history": "restauro del 1934, consolidamento con malta di calce",
    "provenance_history": "scavi Boni 1899; poi Antiquarium Forense",
    "exhibition_history": "mostra «Roma antica», 1911",
    "publication_history": "Boni 1900, p. 12; Lanciani 1902",
    "ownership_chain": "collezione Farnese, poi Borbone",
}


@pytest.mark.parametrize("quale", sorted(_PROSE_QUALIA))
def test_each_marked_quale_leaves_with_its_tag(tmp_path, quale):
    g = Graph("qualia")
    g.add_node(PropertyNode("p1", quale, value=_PROSE_QUALIA[quale],
                            property_type=quale))
    g.add_node(PropertyNode("p2", "inventory_number", value="MNR 12345",
                            property_type="inventory_number"))
    api.set_working_language(g, "it")
    exporter, store, _ = _export(g, tmp_path)
    prose = _one(store, _iri(exporter, g, "p1"), CRM.P90_has_value)
    assert prose == Literal(_PROSE_QUALIA[quale], lang="it")
    code = _one(store, _iri(exporter, g, "p2"), CRM.P90_has_value)
    assert code.language is None


def test_attribution_has_fields_and_no_note_so_it_is_not_marked():
    """Measured: its schema is an actor reference, a closed list and a float.
    The rule marks only the note, and there is none."""
    dm = _Datamodel()
    node = PropertyNode("p", "attribution", value="attributed to Phidias",
                        property_type="attribution")
    assert not dm.is_natural_language(node, "value")
    assert sorted(dm._qualia_natural_language) == sorted(
        ["narrative_content", *_PROSE_QUALIA])
