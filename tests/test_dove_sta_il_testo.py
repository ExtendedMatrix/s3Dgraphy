"""Where the text lives (dev27, A3; E.D. 2026-10-01, *il testo, la risorsa e la
selezione*), on the Vitruvius fixture (``tests/fixtures/vitruvio/``).

* the document is the work: its fields describe it, and hold none of its text;
* each resource says the language(s) of its CONTENT (``data.lang``, a tag or a
  sorted list), which does not enter the cascade of its own description and
  leaves as ``dcterms:language``;
* the extractor carries the passage, ``@la``, with the Italian translation from
  an edition beside it and the English AI one only where AI may go;
* the fixture rebuilds byte for byte, imports, and re-exports identically.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal  # noqa: E402
from rdflib.compare import isomorphic  # noqa: E402
from rdflib.namespace import DCTERMS  # noqa: E402

from s3dgraphy import api  # noqa: E402
from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402
from s3dgraphy.language import node_language  # noqa: E402

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "vitruvio")
sys.path.insert(0, HERE)
import build as vitruvio  # noqa: E402


def _store(path):
    s = rdflib.Graph()
    s.parse(path, format="turtle")
    return s


def _iri(g, nid):
    return RDFExporter("x.ttl")._node_iri(g.graph_id, nid)


def _body(doc):
    """The document without its ``header``: the header records which build and
    which datamodel versions wrote the file, and moves at every bump; what the
    fixture shows is the body."""
    return {k: v for k, v in json.loads(json.dumps(doc, sort_keys=True)).items()
            if k != "header"}


def test_the_fixture_rebuilds_byte_for_byte(tmp_path):
    vitruvio.write(str(tmp_path))
    for name in ("vitruvio_round_trip.ttl", "vitruvio_publish.ttl"):
        with open(os.path.join(HERE, name), encoding="utf-8") as a, \
                open(tmp_path / name, encoding="utf-8") as b:
            assert a.read() == b.read(), name
    with open(os.path.join(HERE, "vitruvio.em.json"), encoding="utf-8") as a, \
            open(tmp_path / "vitruvio.em.json", encoding="utf-8") as b:
        assert _body(json.load(a)) == _body(json.load(b))


def test_the_em_json_imports_and_reexports_identically():
    with open(os.path.join(HERE, "vitruvio.em.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    g, warnings = parse_emjson(doc)
    assert not [w for w in warnings if "unknown" in w]
    assert _body(build_emjson(g)) == _body(doc)


@pytest.mark.parametrize("mode", ["round_trip", "publish"])
def test_the_ttl_imports_and_reexports_identically(tmp_path, mode):
    path = os.path.join(HERE, f"vitruvio_{mode}.ttl")
    g = RDFImporter().parse(path)[0]
    out = RDFExporter(str(tmp_path / "again.ttl"), format="turtle",
                      mode=mode).export_single_graph(g)
    assert isomorphic(_store(path), _store(out))


def test_the_extractor_leaves_la_with_its_translations():
    g = vitruvio.build()
    rt = _store(os.path.join(HERE, "vitruvio_round_trip.ttl"))
    pub = _store(os.path.join(HERE, "vitruvio_publish.ttl"))
    ext = _iri(g, "vitr.01")
    assert set(rt.objects(ext, DCTERMS.description)) == {
        Literal(vitruvio.LATIN, lang="la"), Literal(vitruvio.ITALIAN, lang="it"),
        Literal(vitruvio.ENGLISH, lang="en")}
    # in a publication the unverified AI translation is out
    assert set(pub.objects(ext, DCTERMS.description)) == {
        Literal(vitruvio.LATIN, lang="la"), Literal(vitruvio.ITALIAN, lang="it")}


def test_the_document_is_the_work_and_holds_no_passage():
    g = vitruvio.build()
    doc = g.find_node_by_id("vitr")
    assert vitruvio.LATIN not in (doc.description or "")
    assert node_language(doc) == "it"          # born in the study


def test_a_resource_says_the_language_of_its_content():
    g = vitruvio.build()
    scan, page = g.find_node_by_id("scan"), g.find_node_by_id("lacus")
    assert api.content_languages(scan) == ["it", "la"]
    assert api.content_languages(page) == ["la"]
    # ...which is not the language of its description
    assert node_language(page) is None
    pub = _store(os.path.join(HERE, "vitruvio_publish.ttl"))
    assert set(pub.objects(_iri(g, "scan"), DCTERMS.language)) == {
        Literal("it"), Literal("la")}
    back = RDFImporter().parse(os.path.join(HERE, "vitruvio_publish.ttl"))[0]
    assert back.find_node_by_id("scan").data["lang"] == ["it", "la"]
    assert back.find_node_by_id("lacus").data["lang"] == "la"


def test_content_languages_refuse_what_is_not_a_tag():
    g = vitruvio.build()
    scan = g.find_node_by_id("scan")
    with pytest.raises(ValueError):
        api.set_content_languages(scan, ["la", "latino"])
    assert scan.data["lang"] == ["it", "la"]           # nothing written
    assert api.set_content_languages(scan, None) == []
    assert "lang" not in scan.data
    with pytest.raises(ValueError):
        api.set_content_languages(g.find_node_by_id("vitr"), "la")
