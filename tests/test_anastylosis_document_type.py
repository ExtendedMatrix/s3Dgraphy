"""The anastylosis as a dynamic document (MICRO special find e fine
dell'unità, part 5, E.D. 23 Oct 2026): a TYPE of document in
em_document_types.json — vocabulary, not an extension."""

import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"


def _types():
    return json.loads((CONFIG / "em_document_types.json").read_text(encoding="utf-8"))


def test_the_type_is_declared_with_its_reading():
    doc = _types()
    assert doc["metadata"]["version"] == "2.1"
    t = doc["document_types"]["anastylosis"]
    assert "findspot" in t["description"] and "original position" in t["description"]
    assert "VERSIONS" in t["description"]
    reading = t["em_reading"]
    assert "paradata of the VSF" in reading["argument"]
    assert "combiner" in reading["argument"]
    assert "Anastylosis" in reading["act"]
    assert "simulation of the collapse" in reading["reverse"]
    sub = t["subtypes"]["anastylosis_trajectories"]
    assert {"findspot_position", "original_position"} <= set(sub["possible_extractions"])
    assert "version" in sub["metadata_requirements"]["mandatory"]


def test_nothing_is_invented():
    t = _types()["document_types"]["anastylosis"]
    # a document is an E31 that documents (P70) what it is about
    assert t["vocabulary_mappings"]["cidoc_crm"] == {"class": "E31_Document",
                                                     "property": "P70_documents"}
    # the AAT id was not verified: it is left empty, with the reason
    assert t["vocabulary_mappings"]["getty_aat"] is None
    assert "never from memory" in t["vocabulary_mappings"]["_getty_aat_note"]
