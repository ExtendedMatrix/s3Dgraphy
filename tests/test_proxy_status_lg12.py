"""MICRO-LG12 (E.D., 23 Nov 2026) — the proxy not drawn yet: a placeholder for
source-based modeling. The property ``proxy_status`` of a unit (state,
placeholder, candidate sources with their strength), the deterministic and AI
scouting, the list of the units to draw.
"""
from __future__ import annotations

import json
import os

import pytest

from s3dgraphy import Graph
from s3dgraphy import proxy_status as PS
from s3dgraphy.geometry.proxy import create_geometry_proxy
from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import (DocumentaryStratigraphicUnit, StratigraphicUnit)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLU = os.path.join(HERE, "..", "..", "_datasets", "templumare-v11",
                      "TempluMare_v11_fu-prova_proxy.em.json")


def _site():
    """A wall drawn (W1), a USD not drawn (D3) described by the report R75,
    a real US not drawn (S5) on the wall, a survey of 2015 (D01 → RM15) and a
    reconstruction of the II century (D09 → RM2)."""
    g = Graph("LG12")
    for eid, name, s, e in (("ROM", "II A.D.", 100, 199), ("POST", "Post antiquity", 200, 1800),
                            ("Y15", "2015", 2015, 2015)):
        g.add_node(EpochNode(eid, name, s, e))
    g.add_node(StratigraphicUnit("W1", "SU001"))
    g.add_edge("fe_W1", "W1", "ROM", "has_first_epoch")
    g.add_node(StratigraphicUnit("S5", "SU005"))
    g.add_edge("fe_S5", "S5", "POST", "has_first_epoch")
    g.add_edge("ov", "S5", "W1", "overlies")
    g.add_node(DocumentaryStratigraphicUnit("D3", "USD003", description="post-Roman drainage channels"))
    g.add_edge("fe_D3", "D3", "POST", "has_first_epoch")
    g.add_node(DocumentNode("R75", "D.02", description="report of the 1975 excavation"))
    g.add_node(PropertyNode("D3def", "definition", value="channels", property_type="definition"))
    g.add_edge("d3p", "D3", "D3def", "has_property")
    g.add_node(ExtractorNode("X1", "D.02.1", description="p. 12"))
    g.add_edge("x1a", "D3def", "X1", "has_data_provenance")
    g.add_edge("x1b", "X1", "R75", "extracted_from")
    for did, name in (("D01", "D.01"), ("D09", "D.09")):
        g.add_node(DocumentNode(did, name))
    g.add_node(RepresentationModelNode("RM15", "Survey 2015"))
    g.add_edge("rm15a", "Y15", "RM15", "has_representation_model")
    g.add_edge("rm15b", "D01", "RM15", "has_representation_model")
    g.add_node(RepresentationModelNode("RM2", "Reconstruction II AD"))
    g.add_edge("rm2a", "ROM", "RM2", "has_representation_model")
    g.add_edge("rm2b", "D09", "RM2", "has_representation_model")
    create_geometry_proxy(g, "W1", {"url": "proxies/SU001.glb"})
    g.add_node(AuthorNode("ED", orcid="0000-0002-0000-0000", name="Emanuel", surname="Demetrescu"))
    return g


SQUARE = [[0, 0], [4, 0], [4, 4], [0, 4]]


def test_qualia_datamodel_and_translations_declare_proxy_status():
    from s3dgraphy.tools import datamodel_i18n as D
    here = os.path.join(HERE, "..", "src", "s3dgraphy", "JSON_config")
    q = json.load(open(os.path.join(here, "em_qualia_types.json")))
    ps = q["property_names"]["proxy_status"]
    assert set(ps["values"]) == set(PS.STATES)
    assert set(ps["source_strengths"]) == set(PS.STRENGTHS)
    assert "USE:" in ps["scope_note"] and "DO NOT USE:" in ps["scope_note"] and "NARRATIVE:" in ps["scope_note"]
    assert ps["rdf"]["class"] == "crm:E13_Attribute_Assignment"
    nd = json.load(open(os.path.join(here, "s3Dgraphy_node_datamodel.json")))
    sub = nd["paradata_nodes"]["ParadataNode"]["subtypes"]
    assert sub["PropertyNode"]["properties"]["placeholder"]["em_json"] == "data.placeholder"
    assert sub["ExtractorNode"]["properties"]["source_strength"]["em_json"] == "data.source_strength"
    assert sub["ExtractorNode"]["properties"]["source_model"]["em_json"] == "data.source_model"
    assert D.property_name_label("proxy_status", "it") == "Stato del proxy"
    assert D.property_value_label("proxy_status", "not_yet_drawn", "it") == "non ancora disegnato"
    assert D.property_name_text("proxy_status", "strength_to_verify", "it") == "da verificare"
    assert D.property_name_text("proxy_status", "scope_note", "it").startswith("USARE:")
    ttl = open(os.path.join(here, "em.ttl")).read()
    for c in ("ProxyDrawn", "ProxyNotYetDrawn", "ProxyNotDrawnByChoice", "ProxyDrawable"):
        assert f"em:{c}\n    a crm:E55_Type" in ttl


def test_drawn_is_read_from_the_graph_and_every_unit_counts():
    g = _site()
    assert PS.has_proxy(g, "W1") and not PS.has_proxy(g, "D3") and not PS.has_proxy(g, "S5")
    assert set(PS.units_without_proxy(g)) == {"S5", "D3"}  # a real US as well as a USD
    st = PS.status(g, "W1")
    assert st["drawn"] and st["state"] == "drawn" and st["declared"] is None
    assert PS.status(g, "S5")["state"] is None  # nothing said


def test_declare_with_placeholder_paradata_and_one_property_per_unit():
    g = _site()
    r = PS.declare(g, "D3", "non ancora disegnato", placeholder="a network of channels",
                   note="E.D.: the documentation is not enough", document_id="R75", author_id="ED")
    st = PS.status(g, "D3")
    assert st["declared"] == "not_yet_drawn" and st["placeholder"] == "a network of channels"
    assert st["statements"] and st["statements"][0]["documents"] == ["R75"]
    assert st["statements"][0]["authors"][0]["id"] == "ED"
    r2 = PS.declare(g, "D3", "drawable")
    assert r2["property_id"] == r["property_id"]
    assert PS.status(g, "D3")["declared"] == "drawable"
    assert PS.status(g, "D3")["placeholder"] == "a network of channels"
    with pytest.raises(ValueError):
        PS.declare(g, "D3", "painted")
    with pytest.raises(ValueError):
        PS.declare(g, "ROM", "drawable")  # an epoch is not a unit


def test_candidate_sources_with_strength_model_and_ai_author():
    g = _site()
    PS.add_source(g, "S5", "D01", "certain", note="the wall top is visible", model_id="RM15", author_id="ED")
    PS.add_source(g, "S5", "R75", "da verificare", ai_model="claude-x", act_start="2026-11-23")
    st = PS.status(g, "S5")
    assert st["declared"] is None  # a source never declares a state
    by_doc = {s["document"]: s for s in st["sources"]}
    assert by_doc["D01"]["strength"] == "certain" and by_doc["D01"]["model"] == "RM15"
    assert by_doc["D01"]["model_name"] == "Survey 2015" and by_doc["D01"]["origin"] == "human"
    ai = by_doc["R75"]
    assert ai["strength"] == "to_verify" and ai["origin"] == "ai" and ai["act_start"] == "2026-11-23"
    assert ai["authors"][0]["ai"] and ai["authors"][0]["model"] == "claude-x"
    # idempotent on (unit, document, model)
    PS.add_source(g, "S5", "D01", "probable", model_id="RM15")
    assert len(PS.status(g, "S5")["sources"]) == 2
    with pytest.raises(ValueError):
        PS.add_source(g, "S5", "D01", "sure")


def test_to_draw_drawable_first_then_by_strength_by_choice_apart():
    g = _site()
    g.add_node(StratigraphicUnit("S6", "SU006"))
    g.add_node(StratigraphicUnit("S7", "SU007"))
    PS.declare(g, "S7", "not_drawn_by_choice", note="earth, no shape on purpose")
    PS.add_source(g, "D3", "R75", "probable")
    PS.add_source(g, "D3", "D01", "probable")
    PS.add_source(g, "S6", "D01", "certain")
    PS.declare(g, "S5", "drawable")
    out = PS.to_draw(g)
    assert [s["name"] for s in out["units"]] == ["SU005", "USD003", "SU006"]
    assert [s["weight"] for s in out["units"]] == [0, 4, 3]
    assert [s["name"] for s in out["by_choice"]] == ["SU007"]
    assert out["units"][1]["description"] == "post-Roman drainage channels"


def test_hints_say_a_placeholder_left_on_a_drawn_unit(tmp_path):
    g = _site()
    PS.declare(g, "W1", "not_yet_drawn")
    (tmp_path / "proxies").mkdir()
    (tmp_path / "proxies" / "SU005.glb").write_bytes(b"glTF")
    kinds = {(h["kind"], h["name"]) for h in PS.hints(g, doc_dir=str(tmp_path))}
    assert kinds == {("declared_but_drawn", "SU001"), ("unlinked_file", "SU005")}
    assert PS.status(g, "W1")["state"] == "drawn"  # never corrected
    assert PS.status(g, "S5", doc_dir=str(tmp_path))["unlinked_file"].endswith("SU005.glb")


def test_deterministic_scouting_extractors_footprints_and_unread_models():
    g = _site()
    fps = {"W1": {"ring": SQUARE}}
    models = {"RM2": {"ring": [[3, 3], [9, 3], [9, 9], [3, 9]]}}
    unread = [{"id": "RM15", "name": "Survey 2015", "why": "tileset"}]
    r = PS.scout_deterministic(g, footprints=fps, model_footprints=models, unread_models=unread)
    got = {(p["unit_name"], p["kind"], p["document_name"], p["model_name"]) for p in r["proposals"]}
    # D3: its extractor cites the report; no neighbour has a shape (no area)
    assert ("USD003", "extractor", "D.02", None) in got
    assert r["no_area"] == ["D3"]
    # S5 (post-antique, alive in 2015) overlies the drawn wall: the 2015 survey
    # cannot be read → unread_footprint; the reconstruction of the II century
    # is not of an epoch of S5 (born after 200)
    assert ("SU005", "unread_footprint", "D.01", "Survey 2015") in got
    assert not any(n == "SU005" and m == "Reconstruction II AD" for n, _k, _d, m in got)
    assert all(p["strength"] == "to_verify" and p["origin"] == "derived" for p in r["proposals"])
    # a source the unit already has is not proposed again
    PS.add_source(g, "D3", "R75", "probable")
    r2 = PS.scout_deterministic(g, footprints=fps, model_footprints=models, unread_models=unread)
    assert not any(p["unit_name"] == "USD003" and p["kind"] == "extractor" for p in r2["proposals"])


def test_deterministic_footprint_meets_the_area_of_the_neighbours():
    g = _site()
    g.add_node(StratigraphicUnit("S8", "SU008"))
    g.add_edge("fe_S8", "S8", "ROM", "has_first_epoch")
    g.add_edge("ab", "S8", "W1", "abuts")
    fps = {"W1": {"ring": SQUARE}}
    near = PS.scout_deterministic(g, units=["S8"], footprints=fps,
                                  model_footprints={"RM2": {"ring": [[3, 3], [9, 3], [9, 9], [3, 9]]}},
                                  unread_models=[])
    assert [(p["kind"], p["model_name"]) for p in near["proposals"]] == [("footprint", "Reconstruction II AD")]
    far = PS.scout_deterministic(g, units=["S8"], footprints=fps,
                                 model_footprints={"RM2": {"ring": [[30, 30], [39, 30], [39, 39]]}},
                                 unread_models=[])
    assert far["proposals"] == []
    assert PS.convex_overlap(SQUARE, [[4, 4], [5, 4], [5, 5]])  # touching counts


def test_ai_briefing_reply_and_acceptance():
    g = _site()
    det = PS.scout_deterministic(g, footprints={}, model_footprints={}, unread_models=[])
    ctx = PS.ai_context(g, deterministic=det, lang="it")
    assert ctx["proxy_scouting"] and {u["name"] for u in ctx["units"]} == {"USD003", "SU005"}
    d3 = next(u for u in ctx["units"] if u["name"] == "USD003")
    assert d3["cited_documents"] == ["D.02"] and d3["definition"] == "channels"
    assert "functional" not in json.dumps(ctx)  # no functional unit, no landscape (community)
    prompt = PS.build_ai_prompt(ctx)
    assert "Italian" in prompt and '"strength"' in prompt
    reply = json.dumps({"proposals": [
        {"unit": "USD003", "document": "D.02", "strength": "probabile", "note": "fig. 4", "why": "the report draws it"},
        {"unit": "SU001", "document": "D.01", "strength": "certain"},          # drawn: refused
        {"unit": "USD003", "document": "D.99", "strength": "certain"},         # no such document
        {"unit": "SU005", "document": "D.01", "model": "Survey 2015", "strength": "maybe"}],
        "placeholders": [{"unit": "USD003", "placeholder": "channels 40 cm wide", "state": "drawable", "why": "p. 12"}]})
    r = PS.parse_ai_reply(g, "```json\n" + reply + "\n```", model="claude-x", date="2026-11-23")
    assert [(p["unit_name"], p["document_name"], p["strength"]) for p in r["proposals"]] == \
        [("USD003", "D.02", "probable"), ("SU005", "D.01", "to_verify")]
    assert r["proposals"][1]["model"] == "RM15"
    assert len(r["dropped"]) == 2
    assert r["placeholders"][0]["state"] == "drawable"
    # nothing is written until a person accepts
    assert PS.status(g, "D3")["sources"] == []
    PS.accept_proposal(g, r["proposals"][0], accepted_by="ED")
    s = PS.status(g, "D3")["sources"][0]
    assert s["origin"] == "ai" and s["strength"] == "probable" and s["act_start"] == "2026-11-23"
    assert {a["id"] for a in s["authors"]} >= {"ED"} and any(a["ai"] for a in s["authors"])
    assert "fig. 4" in s["note"] and "the report draws it" in s["note"]
    # a deterministic proposal: origin derived
    PS.accept_proposal(g, det["proposals"][0], accepted_by="ED")
    assert any(x["origin"] == "derived" for x in PS.status(g, det["proposals"][0]["unit"])["sources"])
    # the echo reply is valid
    echo = PS.parse_ai_reply(g, PS.echo_reply(ctx), model="echo-1")
    assert echo["dropped"] == [] and echo["placeholders"]


def test_rdf_the_proxy_status_is_an_attribute_assignment(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Namespace, RDF
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g = _site()
    PS.declare(g, "D3", "not_yet_drawn", placeholder="channels")
    pid = PS.status(g, "D3")["property"]
    path = tmp_path / "lg12.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    EM = Namespace("https://w3id.org/em/ontology#")

    def iri(nid):
        return next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/node/" + nid))
    assert (iri("D3"), CRM.P140i_was_attributed_by, iri(pid)) in store
    assert (iri(pid), RDF.type, CRM.E13_Attribute_Assignment) in store
    assert (iri(pid), CRM.P2_has_type, EM.ProxyNotYetDrawn) in store


def test_emjson_round_trip_keeps_state_placeholder_and_sources():
    from s3dgraphy import api
    g = _site()
    PS.declare(g, "D3", "drawable", placeholder="channels")
    PS.add_source(g, "D3", "D01", "certain", model_id="RM15", note="visible")
    doc = json.loads(json.dumps(api.graph_to_emjson(g)))
    g2, _w = api.load_emjson(doc)
    st = PS.status(g2, "D3")
    assert st["declared"] == "drawable" and st["placeholder"] == "channels"
    assert [(s["document"], s["strength"], s["model"]) for s in st["sources"]] == [("D01", "certain", "RM15")]


@pytest.mark.skipif(not os.path.isfile(TEMPLU), reason="the Templu dataset of MICRO-LG12 is not here")
def test_templu_usd003_usd004_declared():
    from s3dgraphy import api
    g, _w = api.load_emjson(json.load(open(TEMPLU)))
    by_name = {n.name: n.node_id for n in g.nodes}
    for name in ("USD003", "USD004"):
        st = PS.status(g, by_name[name])
        assert st["declared"] == "not_yet_drawn" and st["placeholder"]
        assert st["sources"], name
    names = [s["name"] for s in PS.to_draw(g)["units"]]
    assert "USD003" in names and "USD004" in names
