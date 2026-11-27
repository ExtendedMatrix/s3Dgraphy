"""MICRO-BK1 · `declared.as_of` is when the declaration was SAID.

A photograph taken in 2015 and deposited today with a licence declared today:
the stamp's act is dated by the capture (`by.at`), and its `declared` block must
not claim the licence was in force «as of» the day of the photograph.
"""
from s3dgraphy import api
from s3dgraphy.stamp.emit import emit_stamp

ORCID = "0000-0002-1825-0097"
DIGEST = "sha256:" + "a" * 64


def _graph():
    doc = {"header": {"format": "em.json", "version": "1.0"},
           "graph": {"graph_id": "bk1", "nodes": [
               {"id": "res:1", "node_type": "resource", "name": "scatto-01.jpg",
                "data": {"checksum": DIGEST, "media_type": "image/jpeg"}}],
               "edges": []}}
    graph, _warnings = api.load_emjson(doc)
    api.bucket_acquisition(graph, ["res:1"], name="photo · Aiano 2015",
                           dtc_kind="photo", author=ORCID,
                           at="2015-07-03T00:00:00Z")
    return graph


def test_as_of_is_the_declaration_not_the_capture():
    graph = _graph()
    api.enrich_asset_dtc(graph, DIGEST, attributor=ORCID, license="CC-BY-4.0",
                         embargo="2027-01-01", at="2026-11-27T10:00:00Z")
    stamp = emit_stamp(graph, "res:1")
    assert stamp["by"]["at"] == "2015-07-03T00:00:00Z"
    assert stamp["declared"]["license"] == "CC-BY-4.0"
    assert stamp["declared"]["embargo_until"] == "2027-01-01"
    assert stamp["declared"]["as_of"] == "2026-11-27T10:00:00Z"
    assert stamp["declared"]["by"]["id"] == f"https://orcid.org/{ORCID}"


def test_two_signatures_keep_the_act_date():
    """Licence and embargo said by two people: no single instant to name, so
    the act's date stays (as before), and `by` is silent."""
    graph = _graph()
    api.enrich_asset_dtc(graph, DIGEST, attributor=ORCID, license="CC-BY-4.0",
                         at="2026-11-27T10:00:00Z")
    api.enrich_asset_dtc(graph, DIGEST, attributor="0000-0003-1111-1112",
                         embargo="2027-01-01", at="2026-11-28T10:00:00Z")
    stamp = emit_stamp(graph, "res:1")
    assert stamp["declared"]["as_of"] == "2015-07-03T00:00:00Z"
    assert "by" not in stamp["declared"]
