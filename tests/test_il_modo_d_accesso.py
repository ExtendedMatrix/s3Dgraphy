"""How the hand of a signature had entered (dev27, for EMStudio E1; E.D.
2026-10-01, *l'accesso sul campo*).

A signature — who created, who last edited, who verified — carries the access
mode beside it: ``orcid`` (verified by ORCID) or ``node_password`` (attested by a
StratiGraph node, offline). Every guard on a case that makes it fire.
"""

from __future__ import annotations

import pytest

from s3dgraphy import api
from s3dgraphy.crdt import apply_op_to_section, make_op
from s3dgraphy.editorial import normalize_auth
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

ORCID = "0000-0002-1825-0097"
FIELD = {"mode": "node_password", "attested_by": "fcn-segni"}


def test_the_two_modes_and_what_is_refused():
    assert normalize_auth("orcid") == {"mode": "orcid"}
    assert normalize_auth(FIELD) == FIELD
    assert normalize_auth(None) is None
    for bad in ("password", {"mode": "node_password"},
                {"mode": "orcid", "attested_by": "fcn"}):
        with pytest.raises(ValueError):
            normalize_auth(bad)


def test_stamps_carry_the_mode_beside_the_hand():
    us = StratigraphicUnit("us1", "US 1")
    api.stamp_created(us, by=ORCID, auth=FIELD, at="2026-10-31T09:00:00Z")
    assert us.data["created_auth"] == FIELD
    api.stamp_modified(us, by=ORCID, auth="orcid", at="2026-10-31T10:00:00Z")
    assert us.data["modified_auth"] == {"mode": "orcid"}
    # a new hand without a mode: the previous mode is not left as if it were its
    api.stamp_modified(us, by="0000-0001-5109-3700")
    assert "modified_auth" not in us.data
    # no hand, no mode
    bare = StratigraphicUnit("us2", "US 2")
    api.stamp_created(bare, auth=FIELD)
    assert "created_auth" not in bare.data
    with pytest.raises(ValueError):
        api.stamp_created(StratigraphicUnit("us3", "US 3"), by=ORCID, auth="x")


def _graph():
    g = Graph("g")
    g.add_node(AuthorNode("ed", name="E", orcid=ORCID, surname="D"))
    d = DocumentNode("d1", "D.1", "firmitas")
    d.data = {"lang": "la"}
    g.add_node(d)
    api.set_working_language(g, "it")
    return g


def test_a_verification_and_a_translation_carry_the_mode():
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità", by="ed",
                            review=True, auth=FIELD)
    assert t.data["created_auth"] == FIELD
    out = api.verify(g, t, "ed", auth=FIELD)
    assert out["validated_auth"] == FIELD and t.data["validated_auth"] == FIELD
    api.verify(g, t, "ed")                    # re-signed without a mode
    assert "validated_auth" not in t.data


def test_the_crdt_writes_the_mode_of_the_op_and_refuses_a_bad_one():
    sec = {"nodes": [], "edges": []}
    op = make_op("add_node", ts="2026-10-31T09:00:00Z", author=ORCID, auth=FIELD,
                 node={"id": "us1", "node_type": "US", "name": "US 1",
                       "data": {"lang": "it"}})
    assert apply_op_to_section(sec, op).applied
    us = sec["nodes"][0]
    assert us["data"]["created_auth"] == FIELD and us["data"]["modified_auth"] == FIELD
    op = make_op("update_field", ts="2026-10-31T10:00:00Z", author=ORCID,
                 auth="orcid", node_id="us1", field="description", value="strato")
    assert apply_op_to_section(sec, op).applied
    assert us["data"]["modified_auth"] == {"mode": "orcid"}
    assert us["data"]["created_auth"] == FIELD
    bad = make_op("update_field", ts="2026-10-31T11:00:00Z", author=ORCID,
                  auth="password", node_id="us1", field="description", value="x")
    res = apply_op_to_section(sec, bad)
    assert not res.applied and us["description"] == "strato"


rdflib = pytest.importorskip("rdflib")

from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402


def test_the_mode_goes_through_rdf_and_back(tmp_path):
    g = _graph()
    t = api.add_translation(g, "d1", "description", "it", "solidità", by="ed",
                            review=True, auth=FIELD, at="2026-10-31T09:00:00Z")
    api.verify(g, t, "ed", auth="orcid", at="2026-10-31T10:00:00Z")
    first, _ = parse_emjson(build_emjson(g))
    path = RDFExporter(str(tmp_path / "g.ttl"), format="turtle"
                       ).export_single_graph(first)
    text = (tmp_path / "g.ttl").read_text()
    assert "em:attestedBy \"fcn-segni\"" in text and "em:authMode" in text
    back, _ = parse_emjson(build_emjson(RDFImporter().parse(path)[0]))
    got = back.find_node_by_id(t.node_id).data
    assert got["created_auth"] == FIELD
    assert got["validated_auth"] == {"mode": "orcid"}
