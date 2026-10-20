"""CRMem as a browsable page: every term of em.ttl gets an entry, and the
published copy of em.ttl carries the commit it comes from."""

import re

import rdflib
from rdflib.namespace import OWL, RDF

from s3dgraphy.tools import ontology_html as oh


def test_every_em_term_has_an_entry_and_the_copy_is_stamped(tmp_path):
    page = oh.build(tmp_path)
    html = page.read_text(encoding="utf-8")
    g = rdflib.Graph()
    g.parse(oh.EM_TTL, format="turtle")
    terms = {str(s)[len(oh.EM):] for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty)
             for s in g.subjects(RDF.type, t) if str(s).startswith(oh.EM)}
    ids = set(re.findall(r'<article class="entry" id="([^"]+)"', html))
    assert ids == terms
    version = str(g.value(next(g.subjects(RDF.type, OWL.Ontology)), OWL.versionInfo))
    assert f"CRMem version {version}" in html
    copy = (tmp_path / "em.ttl").read_text(encoding="utf-8")
    assert copy.startswith(f"# Published copy of CRMem {version}.")
    assert "commit" in copy.splitlines()[1]
    rdflib.Graph().parse(data=copy, format="turtle")      # the stamp keeps it valid Turtle
    xml = rdflib.Graph().parse(tmp_path / "em.rdf", format="xml")
    assert len(xml) == len(g)                              # RDF/XML is the same graph
