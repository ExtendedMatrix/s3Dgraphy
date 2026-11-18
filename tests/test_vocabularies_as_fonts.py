"""MICRO-U-VOCABOLARI-COME-FONT (E.D., 18 Nov 2026): vocabulary packages
installed on the machine like fonts, the double value on a node (code of the
term + label written + vocabulary and version), the warnings «not controlled»
and «missing vocabulary», the guided link, the declaration in the em.json."""
import hashlib
import io
import json
import zipfile

import pytest

from s3dgraphy import terms as T
from s3dgraphy.authorities import packages as P
from s3dgraphy.authorities import resolve
from s3dgraphy.container import (Container, build_container, content_digest,
                                 parse_container)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.property_node import PropertyNode

ICCD = "http://dati.beniculturali.it/vocabularies/materia_e_tecnica-ra/def/"
AAT = "http://vocab.getty.edu/aat/"

RDFXML = f"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#">
<rdf:Description rdf:about="{ICCD}031">
  <rdf:type rdf:resource="http://www.w3.org/2004/02/skos/core#Concept"/>
  <skos:prefLabel xml:lang="it">calcare</skos:prefLabel>
  <skos:narrower rdf:resource="{ICCD}031.001"/>
</rdf:Description>
<rdf:Description rdf:about="{ICCD}031.001">
  <rdf:type rdf:resource="http://www.w3.org/2004/02/skos/core#Concept"/>
  <rdfs:label xml:lang="it">a gradina</rdfs:label>
  <skos:broader rdf:resource="http://th-mtcRa:031"/>
  <skos:prefLabel xml:lang="it">calcare a gradina</skos:prefLabel>
</rdf:Description>
<rdf:Description rdf:about="{ICCD}040">
  <rdf:type rdf:resource="http://www.w3.org/2004/02/skos/core#Concept"/>
  <skos:prefLabel xml:lang="it">piombo</skos:prefLabel>
</rdf:Description>
</rdf:RDF>
""".encode("utf-8")

NT = "\n".join([
    f'<{AAT}300011286> <http://www.w3.org/2004/02/skos/core#prefLabel> "limestone"@en .',
    f'<{AAT}300011286> <http://www.w3.org/2004/02/skos/core#prefLabel> "calcare"@it .',
    f'<{AAT}300011286> <http://www.w3.org/2004/02/skos/core#prefLabel> "Kalkstein"@de .',
    f'<{AAT}300011286> <http://www.w3.org/2004/02/skos/core#altLabel> "lime stone"@en .',
    f'<{AAT}300011286> <http://www.w3.org/2004/02/skos/core#broader> <{AAT}300011176> .',
    f'<{AAT}300011176> <http://www.w3.org/2004/02/skos/core#prefLabel> "sedimentary rock"@en .',
    f'<{AAT}300011176> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2004/02/skos/core#Concept> .',
    f'<{AAT}300011286> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2004/02/skos/core#Concept> .',
    f'<{AAT}300011020> <http://www.w3.org/2004/02/skos/core#prefLabel> "lead (metal)"@en .',
    f'<{AAT}300011020> <http://www.w3.org/2004/02/skos/core#prefLabel> "piombo"@it .',
]).encode("utf-8") + b"\n"


def _manifest(vid, tier, fname, data, **extra):
    m = {"format": P.PACKAGE_FORMAT, "id": vid, "version": "2026-11-18",
         "snapshot_date": "2026-11-18", "languages": [], "license": "x", "tier": tier,
         "attribution": f"attribution of {vid}", "serves": ["material_type"], "facet": "WHAT",
         "source": {"file": f"source/{fname}", "sha256": hashlib.sha256(data).hexdigest()}}
    m.update(extra)
    return m


def _zip(manifest, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        if data is not None and manifest.get("source"):
            z.writestr(manifest["source"]["file"], data)
    return buf.getvalue()


@pytest.fixture
def installed(tmp_path):
    iccd = _manifest("iccd-ra-materia", "B", "m.rdf", RDFXML, index_hints={
        "broader_prefix_map": {"http://th-mtcRa:": ICCD}})
    aat = _manifest("getty-aat-materials", "A", "aat.nt", NT, authority="aat",
                    scheme=AAT)
    p1 = tmp_path / "iccd.emvocab.zip"
    p1.write_bytes(_zip(iccd, RDFXML))
    P.vocab_install(str(p1))
    P.vocab_install(_zip(aat, NT))
    return tmp_path


def _prop(nid, name, value):
    return PropertyNode(node_id=nid, name=name, value=value)


# ── 1 · packages ────────────────────────────────────────────────────────────

def test_install_compiles_the_index_here_and_lists_it(installed):
    have = {s["id"]: s for s in P.vocab_installed()}
    assert set(have) == {"iccd-ra-materia", "getty-aat-materials"}
    assert have["getty-aat-materials"]["languages"] == ["de", "en", "it"]
    assert have["iccd-ra-materia"]["status"] == P.STATUS_READY
    idx = P.vocab_index("iccd-ra-materia")
    # the hierarchy from narrower AND from the broader IRI repaired in the index only
    assert idx["concepts"][ICCD + "031.001"]["broader"] == [ICCD + "031"]
    # MICRO-PL02: one folder per version (<id>/<version>/)
    src = (P.vocab_folder("iccd-ra-materia") / "source" / "m.rdf").read_bytes()
    assert src == RDFXML                       # the source as published


def test_a_source_that_does_not_match_its_hash_is_refused(tmp_path):
    m = _manifest("x-voc", "A", "x.nt", NT)
    with pytest.raises(P.PackageError, match="sha256"):
        P.vocab_install(_zip(m, NT + b"# changed\n"))


def test_tier_c_ships_no_source_and_is_fetched_locally(tmp_path):
    m = _manifest("c-voc", "C", "c.nt", NT, fetch={"url": "https://example.org/c.nt"})
    with pytest.raises(P.PackageError, match="tier C"):
        P.vocab_install(_zip(m, NT))
    stub = dict(m)
    del stub["source"]
    s = P.vocab_install(_zip(stub, None))
    assert s["status"] == P.STATUS_STUB
    got = P.vocab_fetch_local("c-voc", fetch=lambda url: NT)
    assert got["status"] == P.STATUS_READY and got["local_copy"]
    assert not P.redistributable(got)


def test_updates_and_remove(installed):
    offers = [{"id": "getty-aat-materials", "version": "2027-01-01", "snapshot_date": "2027-01-01",
               "url": "x"},
              {"id": "iccd-ra-materia", "version": "2026-11-18", "snapshot_date": "2026-11-18"}]
    ups = P.vocab_updates(offers)
    assert [u["id"] for u in ups] == ["getty-aat-materials"]
    assert P.vocab_remove("iccd-ra-materia") and not P.vocab_remove("iccd-ra-materia")
    assert [s["id"] for s in P.vocab_installed()] == ["getty-aat-materials"]


def test_search_is_exact_then_close_never_identity(installed):
    hits = P.search("Calcare", lang="it", serves="material_type")
    assert hits[0]["match"] == "exact"
    assert {h["vocabulary"] for h in hits if h["match"] == "exact"} == {
        "iccd-ra-materia", "getty-aat-materials"}
    assert any(h["match"] == "close" and h["uri"] == ICCD + "031.001" for h in hits)
    assert all(h["match"] in ("exact", "close") for h in hits)
    # the resolver sees the installed package before the hand-seeded sample
    refs = resolve("limestone", "WHAT")
    assert refs[0]["uri"] == AAT + "300011286" and refs[0]["vocabulary"] == "getty-aat-materials"
    assert not any(r.get("fixture") and r["authority"] == "aat" for r in refs)
    assert all(r["match"] != "sameAs" for r in refs)


# ── 2 · the double value ────────────────────────────────────────────────────

def test_value_label_in_the_language_asked_then_stored_then_missing(installed):
    n = _prop("p1", "Material", "calcare")
    T.set_term(n, {"concept": AAT + "300011286", "label": "calcare", "lang": "it",
                   "vocabulary": "getty-aat-materials", "version": "2026-11-18"})
    assert n.value == "calcare" and n.description == "calcare"
    assert T.value_label(n, "en")["text"] == "limestone"
    assert T.value_label(n, "de")["from"] == T.FROM_VOCABULARY
    fr = T.value_label(n, "fr")                 # AAT has no French here: the stored label
    assert fr["text"] == "calcare" and fr["lang"] == "it"
    P.vocab_remove("getty-aat-materials")
    gone = T.value_label(n, "en")
    assert gone["text"] == "calcare" and gone["missing_vocabulary"] and gone["from"] == T.FROM_STORED
    text_only = _prop("p2", "Material", "Wood and stucco")
    assert T.value_label(text_only, "it") == {
        "text": "Wood and stucco", "lang": None, "from": T.FROM_TEXT, "concept": None,
        "missing_vocabulary": False, "vocabulary": None, "attribution": None}


def test_the_term_reads_from_an_emjson_dict_and_the_definition_keeps_reading():
    from s3dgraphy.nodes.stratigraphic_node import definition_parts
    term = T.make_term(ICCD + "031", "calcare", "it", "iccd-ra-materia", "2018-09")
    assert definition_parts(term) == (ICCD + "031", "calcare")
    node = {"id": "x", "node_type": "property", "name": "material",
            "data": {"value": "calcare", "concept": term}}
    assert T.term_of(node) == term
    with pytest.raises(ValueError):
        T.make_term("calcare", "calcare", "it")


# ── 3 · warnings ────────────────────────────────────────────────────────────

def test_warnings_uncontrolled_and_missing_vocabulary(installed):
    g = Graph(graph_id="g")
    g.add_node(_prop("a", "Material", "Limestone"))
    g.add_node(_prop("b", "height", "2.3"))                 # not a controlled field
    g.add_node(_prop("c", "construction_technique", ""))     # nothing to control
    linked = _prop("d", "material_type", "piombo")
    T.set_term(linked, {"concept": ICCD + "040", "label": "piombo", "lang": "it",
                        "vocabulary": "iccd-ra-materia", "version": "2018-09"})
    g.add_node(linked)
    other = _prop("e", "material", "x")
    T.set_term(other, {"concept": "http://example.org/x", "label": "x", "lang": "en",
                       "vocabulary": "not-here", "version": "1"})
    g.add_node(other)
    recs = T.vocabulary_warnings(g)
    assert [(r["kind"], r["node_id"]) for r in recs] == [
        (T.KIND_UNCONTROLLED, "a"), (T.KIND_MISSING_VOCABULARY, "e")]
    assert all(r["category"] == "vocabulary" for r in recs)
    from s3dgraphy.api import graph_warnings
    assert [r["node_id"] for r in graph_warnings(g, vocabulary=True)
            if r.get("category") == "vocabulary"] == ["a", "e"]


# ── 4 · the guided link ─────────────────────────────────────────────────────

def test_link_one_or_all_with_the_same_text(installed):
    g = Graph(graph_id="g")
    for i, v in enumerate(["Limestone", "limestone", "Lead", "Limestone"]):
        g.add_node(_prop(f"p{i}", "Material", v))
    first = g.find_node_by_id("p0")
    assert len(T.same_text(g, first)) == 3
    cands = T.candidates(first, lang="en")
    assert cands[0]["uri"] == AAT + "300011286" and cands[0]["match"] == "exact"
    touched = T.link(g, first, cands[0], all_same_text=True, text_lang="en")
    assert touched == ["p0", "p1", "p3"]
    assert g.find_node_by_id("p1").value == "limestone"       # the word stays theirs
    assert T.term_of(g.find_node_by_id("p1"))["concept"] == AAT + "300011286"
    assert T.term_of(g.find_node_by_id("p2")) is None
    assert [r["node_id"] for r in T.vocabulary_warnings(g)] == ["p2"]


# ── the declaration in the em.json ──────────────────────────────────────────

def test_the_file_declares_its_vocabularies_and_may_carry_the_terms(installed):
    g = Graph(graph_id="g1")
    n = _prop("p", "Material", "calcare")
    T.set_term(n, {"concept": AAT + "300011286", "label": "calcare", "lang": "it",
                   "vocabulary": "getty-aat-materials", "version": "2026-11-18"})
    g.add_node(n)
    plain = Graph(graph_id="g2")
    plain.add_node(_prop("q", "Material", "calcare"))
    assert T.VOCABULARIES_KEY not in build_container(Container(graphs={"g2": plain}))

    c = Container(graphs={"g1": g}, active_graph_id="g1")
    doc = build_container(c)
    used = doc["vocabularies"]["used"]["getty-aat-materials"]
    assert used["versions_used"] == ["2026-11-18"] and used["concepts_used"] == 1
    assert used["attribution"] == "attribution of getty-aat-materials" and "terms" not in used

    digest = content_digest(doc)
    c.vocabularies = {"embed": True}
    doc2 = build_container(c)
    assert content_digest(doc2) == digest                     # a declaration is not content
    terms = doc2["vocabularies"]["used"]["getty-aat-materials"]["terms"]
    assert terms[AAT + "300011286"]["pref"] == {"de": "Kalkstein", "en": "limestone", "it": "calcare"}

    # opened where the vocabulary is not installed: the copy in the file speaks
    P.vocab_remove("getty-aat-materials")
    back, _ = parse_container(json.loads(json.dumps(doc2)))
    assert back.vocabularies["embed"] is True
    node = next(x for x in back.graphs["g1"].nodes if x.node_id == "p")
    lab = T.value_label(node, "de", embedded=back.vocabularies)
    assert lab["text"] == "Kalkstein" and not lab["missing_vocabulary"]
    again = build_container(back)                             # the copy survives a save
    assert again["vocabularies"] == doc2["vocabularies"]


def test_a_vocabulary_that_may_not_travel_is_declared_never_copied(tmp_path):
    m = _manifest("c-voc", "C", "c.nt", NT, fetch={"url": "https://example.org/c.nt"})
    del m["source"]
    P.vocab_install(_zip(m, None))
    P.vocab_fetch_local("c-voc", fetch=lambda url: NT)
    g = Graph(graph_id="g1")
    n = _prop("p", "Material", "calcare")
    T.set_term(n, {"concept": AAT + "300011286", "label": "calcare", "lang": "it",
                   "vocabulary": "c-voc", "version": "2026-11-18"})
    g.add_node(n)
    doc = build_container(Container(graphs={"g1": g}, vocabularies={"embed": True}))
    entry = doc["vocabularies"]["used"]["c-voc"]
    assert "terms" not in entry and entry["embedded"] is False
