"""Build the Vitruvius fixture (dev27, A3): where the text lives.

    PYTHONPATH=src python tests/fixtures/vitruvio/build.py

Writes, next to this file, ``vitruvio.em.json`` (the record), and its two RDF
projections ``vitruvio_round_trip.ttl`` (everything, the unverified AI
translation too) and ``vitruvio_publish.ttl`` (what leaves the project: no
unverified AI). Deterministic: fixed instants, uuid5 ids — running it twice
gives the same bytes, and ``tests/test_dove_sta_il_testo.py`` checks it.

The shape it shows (E.D. 2026-10-01, *il testo, la risorsa e la selezione*):

* the DocumentNode is the WORK («Vitruvio, De architectura III,2»); its fields
  describe it and hold none of its text;
* the ResourceNodes are its MANIFESTATIONS, sisters of one document: an online
  page of public-domain Latin, kept as a reference (``residency: reference``,
  no bytes, no digest — nothing is downloaded), and a scan of an edition with
  Latin and Italian facing (a PDF that is not there: a fictitious file, so no
  digest either), each with ``data.lang``, the language(s) of its content;
* the ExtractorNode is the SELECTION: the Latin words of the passage in its
  description, ``data.lang: la``; WHERE it reads is an AnnotationRegionNode
  (``region2d``, a box on page 3 of the scan). A ``passage`` would need the
  character offsets in the file, and the file is not here to measure them;
* two translations of the extractor's description: Italian from an edition (a
  second DocumentNode — fictitious, for the test), English by AI, not verified.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: Vitruvius, De architectura III,2,1 (public domain)
LATIN = ("Aedium autem principia sunt, e quibus constat figurarum aspectus.")
ITALIAN = ("I principi dei templi sono quelli da cui dipende l'aspetto delle "
           "loro figure.")
ENGLISH = "The principles of temples are those on which the look of their forms depends."
PAGE = "https://penelope.uchicago.edu/Thayer/L/Roman/Texts/Vitruvius/3*.html"
ORCID = "0000-0002-1825-0097"
ORCID_2 = "0000-0001-5109-3700"


def build():
    from s3dgraphy import api
    from s3dgraphy.graph import Graph
    from s3dgraphy.language import stamp_born_nodes
    from s3dgraphy.nodes.author_node import AuthorAINode, AuthorNode
    from s3dgraphy.nodes.document_node import DocumentNode
    from s3dgraphy.nodes.extractor_node import ExtractorNode
    from s3dgraphy.nodes.resource_node import ResourceNode

    g = Graph("vitruvio")
    api.set_working_language(g, "it")
    g.add_node(AuthorNode("ed", name="Emanuel", orcid=ORCID, surname="D"))
    g.add_node(AuthorNode("sb", name="Simone", orcid=ORCID_2, surname="B"))
    g.add_node(AuthorAINode("claude", name="Claude"))

    before = {n.node_id for n in g.nodes}
    g.add_node(DocumentNode("vitr", "Vitruvio, De architectura III,2",
                            "Libro III, capitolo 2: i tipi di tempio"))
    g.add_node(DocumentNode("ed_it", "Traduzione italiana di prova",
                            "Un'edizione fittizia, per i test"))
    stamp_born_nodes(g, before)                 # born in the study: it

    page = ResourceNode("lacus", "De architectura III (testo latino online)",
                        url=PAGE, residency="reference")
    api.set_content_languages(page, "la")
    g.add_node(page)
    g.add_edge("vitr__has_linked_resource__lacus", "vitr", "lacus",
               "has_linked_resource")

    ext = ExtractorNode("vitr.01", "D.vitr.01", LATIN, data={"lang": "la"})
    g.add_node(ext)
    scan = ResourceNode("scan", "De architectura III, scansione (latino e italiano)",
                        url="vitruvio_III.pdf")
    api.set_content_languages(scan, ["la", "it"])
    g.add_node(scan)
    g.add_edge("vitr__has_linked_resource__scan", "vitr", "scan",
               "has_linked_resource")
    api.place_reading(g, "vitr.01", "scan",
                      {"geometry_kind": "region2d", "shape_kind": "rect",
                       "rect": [0.12, 0.30, 0.38, 0.08], "page": 3})

    api.add_translation(g, "vitr.01", "description", "it", ITALIAN, by="sb",
                        method="edition", edition="ed_it",
                        at="2026-10-31T09:00:00Z")
    api.add_translation(g, "vitr.01", "description", "en", ENGLISH, by="ed",
                        method="ai", ai="claude", model="claude-opus-5-5",
                        at="2026-10-31T09:05:00Z")
    return g


def write(target=HERE):
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g = build()
    with open(os.path.join(target, "vitruvio.em.json"), "w", encoding="utf-8") as fh:
        json.dump(build_emjson(g), fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    for mode in ("round_trip", "publish"):
        RDFExporter(os.path.join(target, f"vitruvio_{mode}.ttl"),
                    format="turtle", mode=mode).export_single_graph(g)
    return g


if __name__ == "__main__":
    sys.exit(0 if write() else 1)
