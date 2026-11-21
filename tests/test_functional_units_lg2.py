"""MICRO-LG2 (21 Nov 2026): the functional unit in time and the Landscape
Matrix of Sarmizegetusa.

A — the datamodel: has_property, changed_from (change_type transformation, the
E81 projection and its return), is_in_location, is_after / has_same_time
widened to the FunctionalUnitNodeGroup; the new is_observed_in (US, SF, USD →
UT); the declared life of the FU, its scale, the dated property.
B — the computations on a minimal SYNTHETIC fixture (villa → castle + stable,
a Roman wall reused): coherence (member alive, child inside its parent,
coverage), presence (interval, members alive, LOD0 footprint, evidence).
C — the import of the table: a synthetic table here; the v1 of Sarmizegetusa
when the dataset is on this machine (counts, warnings).
"""
import csv
import json
from pathlib import Path

import pytest

from s3dgraphy import functional_units as FU
from s3dgraphy import hdto, landscape as L
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.geometry.wkt import polygon_to_wkt, wkt_to_polygons
from s3dgraphy.graph import Graph
from s3dgraphy.importer.landscape_matrix_csv import import_landscape_matrix_csv
from s3dgraphy.nodes.base_node import load_json_mapping
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import FUNCTIONAL_SCALES, FunctionalUnitNodeGroup
from s3dgraphy.nodes.landscape_unit_node import TopographicUnitNode
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (ContinuityNode, DocumentaryStratigraphicUnit,
                                                StratigraphicUnit,
                                                StructuralVirtualStratigraphicUnit)

V1 = Path("/Users/emanueldemetrescu/Documents/GitHub/_datasets/Sarmizegetusa/06_EM/"
          "LandscapeMatrix/landscape-matrix_v1.csv")


# ── A · the datamodel ────────────────────────────────────────────────────────

@pytest.mark.parametrize("edge,src,tgt,ok", [
    ("has_property", "FunctionalUnitNodeGroup", "property", True),
    ("changed_from", "FunctionalUnitNodeGroup", "FunctionalUnitNodeGroup", True),
    ("changed_to", "FunctionalUnitNodeGroup", "FunctionalUnitNodeGroup", True),
    ("is_in_location", "FunctionalUnitNodeGroup", "LocationNodeGroup", True),
    ("is_after", "FunctionalUnitNodeGroup", "FunctionalUnitNodeGroup", True),
    ("has_same_time", "FunctionalUnitNodeGroup", "FunctionalUnitNodeGroup", True),
    ("is_observed_in", "US", "UT", True),
    ("is_observed_in", "SF", "UT", True),
    ("is_observed_in", "USD", "UT", True),
    # refused: a virtual unit is not observed; a −UT observes an absence;
    # a district is a frame of the where; not toward a functional unit
    ("is_observed_in", "USVs", "UT", False),
    ("is_observed_in", "US", "UT0", False),
    ("is_observed_in", "US", "district", False),
    ("is_observed_in", "US", "FunctionalUnitNodeGroup", False),
    ("is_observed_in", "UT", "UT", False),
    ("is_in_location", "FunctionalUnitNodeGroup", "FunctionalUnitNodeGroup", False),
    ("is_in_district", "FunctionalUnitNodeGroup", "district", False),
])
def test_the_connections_of_the_functional_unit(edge, src, tgt, ok):
    assert Graph.validate_connection(src, tgt, edge) is ok


def test_the_datamodel_says_the_declared_life_and_the_scale():
    dm = load_json_mapping("s3Dgraphy_node_datamodel.json")
    fu = dm["group_nodes"]["GroupNode"]["subtypes"]["FunctionalUnitNodeGroup"]
    assert "has NO epoch of its own" not in fu["description"]
    assert "LIFE IS DECLARED" in fu["description"]
    scale = fu["properties"]["scale"]
    assert tuple(scale["values"]) == FUNCTIONAL_SCALES
    assert scale["rdf"]["concepts"]["building"] == "em:FunctionalScaleBuilding"
    pn = dm["paradata_nodes"]["ParadataNode"]["subtypes"]["PropertyNode"]["properties"]
    assert pn["valid_from"]["em_json"] == "data.valid_from"
    conn = load_json_mapping("s3Dgraphy_connections_datamodel.json")
    new = conn["edge_types"]["is_observed_in"]
    assert new["mapping"]["cidoc"] == "P46i_forms_part_of"
    assert "Felicetti" in new["mapping"]["rationale"]
    assert new["reverse"]["name"] == "observes"
    cf = conn["edge_types"]["changed_from"]
    assert cf["attributes"]["change_type"]["values"] == ["transformation"]
    rule = cf["mapping"]["projection_when_attribute"]["values"]["transformation"]
    assert (rule["former"], rule["latter"]) == ("crm:P124_transformed", "crm:P123_resulted_in")


def test_the_translations_of_the_new_edge_and_names():
    from s3dgraphy.tools.datamodel_i18n import edge_label, edge_ui_phrase
    assert edge_label("is_observed_in", "it") == "È osservata in"
    assert edge_ui_phrase("is_observed_in", "as_source", "it") == "{node} osservata in {x}"
    tr = load_json_mapping("datamodel_translations.json")
    assert tr["property_names"]["use"]["label"]["it"] == "Uso"
    assert tr["property_names"]["phase"]["label"]["it"] == "Fase"
    assert tr["entries"]["FunctionalUnitNodeGroup"]["description"]["it"].count("NON ha un'epoca propria") == 0


def test_the_scale_is_a_type_and_unknown_scales_are_refused():
    assert FunctionalUnitNodeGroup("f", "castello", scale="building").scale == "building"
    assert FunctionalUnitNodeGroup("f", "castello").scale is None
    with pytest.raises(ValueError):
        FunctionalUnitNodeGroup("f", "castello", scale="edificio")


# ── B · the fixture: villa → castle + stable ────────────────────────────────

def _epoch(g, eid, name, start, end):
    g.add_node(EpochNode(eid, name, start, end))


def _first(g, uid, eid):
    g.add_edge(f"{uid}_fe_{eid}", uid, eid, "has_first_epoch")


def _member(g, uid, fid):
    g.add_edge(f"{uid}_in_{fid}", uid, fid, "is_in_functional_unit")


def _footprint(g, uid, ring):
    pid = f"{uid}.fp"
    g.add_node(PropertyNode(pid, "footprint", value=polygon_to_wkt([ring]),
                            property_type="footprint"))
    g.add_edge(f"{uid}_hp_{pid}", uid, pid, "has_property")


def _villa_castle():
    """SYNTHETIC. Roman villa (0–400) → in the Middle Ages (1100–1400) part of
    it becomes a castle, the other part a stable. USM1, a Roman wall, is
    reused by the castle (it still stands); USM2, another Roman wall, ended in
    late antiquity (a BR) and yet the castle claims it — the incoherence; USM4,
    a Roman wall, reused by the stable. The castle has a hall (inside its
    life) and a tower declared before it (outside). US7 is medieval and read by
    nobody."""
    g = Graph("VC", name="Villa e castello (sintetico)")
    _epoch(g, "EP_ROM", "Romana", 0, 400)
    _epoch(g, "EP_TARD", "Tardoantica", 400, 600)
    _epoch(g, "EP_MED", "Medievale", 1100, 1400)
    for uid in ("USM1", "USM2", "USM4", "US3"):
        g.add_node(StratigraphicUnit(uid, uid))
        _first(g, uid, "EP_ROM")
    for uid in ("USM10", "USM20", "US7"):
        g.add_node(StratigraphicUnit(uid, uid))
        _first(g, uid, "EP_MED")
    g.add_node(DocumentaryStratigraphicUnit("USD5", "USD5"))
    _first(g, "USD5", "EP_MED")
    g.add_node(StructuralVirtualStratigraphicUnit("USV6", "USV6"))
    _first(g, "USV6", "EP_MED")
    for br, unit in (("BR2", "USM2"), ("BR3", "US3")):
        g.add_node(ContinuityNode(br, br))
        _first(g, br, "EP_TARD")
        g.add_edge(f"{br}_after_{unit}", br, unit, "is_after")

    site = hdto.make_site_place("Colle del castello")
    g.add_node(site)
    villa = FunctionalUnitNodeGroup("VILLA", "villa", scale="building")
    castle = FunctionalUnitNodeGroup("CASTLE", "castello", scale="building")
    stable = FunctionalUnitNodeGroup("STABLE", "stalla", scale="building")
    hall = FunctionalUnitNodeGroup("HALL", "sala", scale="room")
    tower = FunctionalUnitNodeGroup("TOWER", "torre", scale="room")
    for fu, ep in ((villa, "EP_ROM"), (castle, "EP_MED"), (stable, "EP_MED"),
                   (hall, "EP_MED"), (tower, "EP_TARD")):
        g.add_node(fu)
        _first(g, fu.node_id, ep)
    for uid in ("USM1", "USM2", "USM4", "US3"):
        _member(g, uid, "VILLA")
    for uid in ("USM1", "USM2", "USM10", "USD5", "USV6"):
        _member(g, uid, "CASTLE")
    for uid in ("USM4", "USM20"):
        _member(g, uid, "STABLE")
    _member(g, "HALL", "CASTLE")
    _member(g, "TOWER", "CASTLE")
    for fid in ("VILLA", "CASTLE", "STABLE"):
        g.add_edge(f"{fid}_loc", fid, site.node_id, "is_in_location")
    for latter in ("CASTLE", "STABLE"):
        e = g.add_edge(f"{latter}_cf_VILLA", latter, "VILLA", "changed_from")
        e.attributes["change_type"] = "transformation"
        e.attributes["transformation_kind"] = "reuse"
    _footprint(g, "USM1", [[0, 0], [10, 0], [10, 1], [0, 1]])
    _footprint(g, "USM10", [[0, 5], [3, 5], [3, 8], [0, 8]])
    _footprint(g, "USM2", [[20, 0], [30, 0], [30, 1], [20, 1]])
    # the use of the villa as a mansio: a dated property, not a node
    use = PropertyNode("VILLA.use", "use", value="mansio", property_type="use")
    use.data = {"valid_from": 300, "valid_to": 400}
    g.add_node(use)
    g.add_edge("VILLA_hp_use", "VILLA", "VILLA.use", "has_property")
    return g


def test_every_edge_of_the_fixture_is_allowed():
    g = _villa_castle()
    assert not [e for e in g.edges if e.edge_type == "generic_connection"]
    assert not g.warnings


def test_the_life_of_an_identity_is_declared_not_derived():
    g = _villa_castle()
    chron = g.chronology()
    # the castle is younger than its stones: its life is its epoch's
    assert FU.life(g, "CASTLE", chronology=chron) == (1100, 1400)
    assert FU.life(g, "VILLA", chronology=chron) == (0, 400)
    assert FU.handles(g) == ["VILLA", "CASTLE", "STABLE"]
    assert FU.children(g, "CASTLE") == ["HALL", "TOWER"]
    assert FU.members(g, "CASTLE") == ["USM1", "USM2", "USM10", "USD5", "USV6"]
    chain = {(t["former"], t["latter"]): t for t in FU.transformations(g)}
    assert set(chain) == {("VILLA", "CASTLE"), ("VILLA", "STABLE")}
    assert chain[("VILLA", "CASTLE")]["change_type"] == "transformation"
    assert FU.uses(g, "VILLA") == [{"property_id": "VILLA.use", "value": "mansio",
                                    "valid_from": 300, "valid_to": 400}]


def test_coherence_member_alive_child_inside_and_coverage():
    g = _villa_castle()
    c = FU.coherence(g)
    # USM2 ended in late antiquity: not alive in the castle
    assert [(x["unit"], x["member"]) for x in c["members_not_alive"]] == [("CASTLE", "USM2")]
    # USM1, reused, is alive in both lives: no warning for it
    assert not [x for x in c["members_not_alive"] if x["member"] == "USM1"]
    # the tower declared in late antiquity is outside the castle
    assert [(x["child"], x["parent"]) for x in c["children_outside"]] == [("TOWER", "CASTLE")]
    assert len(c["warnings"]) == 2 and c["warnings"][0].startswith("[functional]")
    it = FU.coherence(g, lang="it")["warnings"]
    assert it[0].startswith("[funzionale] USM2 non è viva nella vita di castello")
    # coverage, a measure: in the Middle Ages US7 is read by nobody
    med = c["coverage"]["EP_MED"]
    assert "US7" in med["unread"]
    assert {"USM1", "USM10", "USM20", "USM4", "USD5", "USV6"}.isdisjoint(med["unread"])
    assert med["read"] == med["alive"] - len(med["unread"])
    # in late antiquity the villa is gone and nothing reads the surviving walls
    assert set(c["coverage"]["EP_TARD"]["unread"]) >= {"USM1", "USM4"}


def test_presence_interval_members_footprint_and_evidence():
    g = _villa_castle()
    p = FU.presence(g, "CASTLE", {"start": 1200, "end": 1300})
    assert p["interval"] == (1200, 1300)
    # the members alive: the reused Roman wall yes, the destroyed one no,
    # and through the hall nothing more (it has no member)
    assert set(p["members_alive"]) == {"USM1", "USM10", "USD5", "USV6"}
    assert p["evidence"] == FU.STRATIGRAPHIC
    assert p["members_by_degree"][FU.DOCUMENTARY] == ["USD5"]
    crs, shape, polys = wkt_to_polygons(p["footprint"])
    assert shape == "MULTIPOLYGON" and len(polys) == 2
    assert p["footprint_parts"] == ["USM1", "USM10"]
    assert p["sites"] == [hdto.site_place_id("Colle del castello")]
    # outside its life: no presence
    none = FU.presence(g, "CASTLE", (100, 300))
    assert none["interval"] is None and none["members_alive"] == [] and none["evidence"] is None
    # the villa in the Roman age: its footprint from the two walls that have one
    villa = FU.presence(g, "VILLA", (100, 200))
    assert set(villa["footprint_parts"]) == {"USM1", "USM2"}


def test_the_degree_of_evidence_is_read_from_the_members():
    g = _villa_castle()
    assert FU.evidence(g, ["USD5"]) == FU.DOCUMENTARY
    assert FU.evidence(g, ["USV6"]) == FU.RECONSTRUCTIVE
    assert FU.evidence(g, ["USD5", "USV6"]) == FU.DOCUMENTARY
    assert FU.evidence(g, []) == FU.SYMBOL
    assert FU.presence(g, "HALL")["evidence"] == FU.SYMBOL


def test_the_landscape_matrix_has_a_row_per_handle():
    g = _villa_castle()
    lg = Graph("LG", name="Paesaggio")
    lg.add_node(hdto.make_site_place("Colle del castello"))
    container = Container(graphs={"LG": lg, "VC": g}, active_graph_id="LG",
                          header={"title": "t", "kind": "landscape", "composition": [{"id": "VC"}]})
    lm = L.landscape_matrix(lg, container)
    rows = {r["node_id"]: r for r in lm["rows"] if r["kind"] == "functional_unit"}
    assert set(rows) == {"VILLA", "CASTLE", "STABLE"}
    assert rows["CASTLE"]["changed_from"] == ["VILLA"]
    assert rows["CASTLE"]["scale"] == "building"
    assert rows["CASTLE"]["evidence"] == FU.STRATIGRAPHIC
    assert rows["CASTLE"]["site_id"] == hdto.site_place_id("Colle del castello")
    assert (rows["CASTLE"]["start"], rows["CASTLE"]["end"]) == (1100, 1400)
    assert rows["VILLA"]["key"] == "VC:VILLA"


def test_emjson_round_trip_keeps_scale_change_type_and_dated_use():
    g = _villa_castle()
    doc = build_container(Container(graphs={"VC": g}, active_graph_id="VC", header={"title": "t"}))
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    assert warnings == []
    back = again.graphs["VC"]
    assert back.find_node_by_id("CASTLE").data.get("scale") == "building"
    cf = [e for e in back.edges if e.edge_type == "changed_from" and e.edge_source == "CASTLE"]
    assert cf and cf[0].attributes.get("change_type") == "transformation"
    assert back.find_node_by_id("VILLA.use").data.get("valid_from") == 300


def test_rdf_projection_of_the_transformation_and_back(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Namespace, RDF
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    from s3dgraphy.importer.rdf_importer import RDFImporter
    g = _villa_castle()
    ut = TopographicUnitNode("UT1", name="UT1")
    g.add_node(ut)
    g.add_edge("USM1_obs_UT1", "USM1", "UT1", "is_observed_in")
    path = tmp_path / "vc.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    EM = Namespace("https://w3id.org/em/ontology#")

    def iri(nid):
        return next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/node/" + nid))

    events = list(store.subjects(RDF.type, CRM.E81_Transformation))
    assert len(events) == 2
    castle_event = [e for e in events if (e, CRM.P123_resulted_in, iri("CASTLE")) in store]
    assert castle_event and (castle_event[0], CRM.P124_transformed, iri("VILLA")) in store
    assert (iri("CASTLE"), CRM.P123i_resulted_from, iri("VILLA")) in store
    assert (iri("CASTLE"), CRM.P2_has_type, EM.FunctionalScaleBuilding) in store
    assert (iri("USM1"), CRM.P46i_forms_part_of, iri("UT1")) in store

    back = RDFImporter().parse(str(path))[0]
    ids = {n.node_id for n in back.nodes}
    assert not any("/transformation/" in i for i in ids)  # the event is no node
    cf = {(e.edge_source, e.edge_target): e for e in back.edges if e.edge_type == "changed_from"}
    assert cf[("CASTLE", "VILLA")].attributes.get("change_type") == "transformation"
    assert cf[("STABLE", "VILLA")].attributes.get("change_type") == "transformation"
    assert back.find_node_by_id("CASTLE").data.get("scale") == "building"
    obs = [(e.edge_source, e.edge_target) for e in back.edges if e.edge_type == "is_observed_in"]
    assert obs == [("USM1", "UT1")]
    # the members came back as members, not as observations
    assert ("USM1", "CASTLE") in {(e.edge_source, e.edge_target) for e in back.edges
                                  if e.edge_type == "is_in_functional_unit"}


def test_a_changed_from_without_change_type_projects_no_event(tmp_path):
    pytest.importorskip("rdflib")
    import rdflib
    from rdflib import RDF, Namespace
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g = _villa_castle()
    for e in g.edges:
        e.attributes.pop("change_type", None)
    path = tmp_path / "vc.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    assert not list(store.subjects(RDF.type, CRM.E81_Transformation))


# ── C · the import of the table ──────────────────────────────────────────────

_COLUMNS = ["riga_v0", "tipo_riga", "sito_id", "sito", "dove (GIS/fonte)", "identita", "scala",
            "da", "a", "orizzonte", "ingresso_da", "tipo_cambio", "evidenza", "fonte", "note",
            "da_anno", "a_anno", "revisione_2026-11-21"]


def _row(**kw):
    r = {c: "" for c in _COLUMNS}
    r.update(kw)
    return r


def _synthetic_table(path):
    rows = [
        _row(riga_v0="1", tipo_riga="identità", sito_id="S01", sito="Colle", identita="villa",
             scala="edificio", da="I sec.", a="IV sec.", fonte="Rossi 2000", da_anno="1", a_anno="400"),
        _row(riga_v0="2", tipo_riga="identità", sito_id="S01", sito="Colle", identita="castello",
             scala="edificio", da="XII sec.", a="oggi", ingresso_da="S01 villa",
             tipo_cambio="trasformazione (riuso)", fonte="Bianchi 2010", da_anno="1100"),
        _row(riga_v0="3", tipo_riga="identità", sito_id="S02", sito="Porta", identita="porta di legno",
             scala="edificio", da="100", a="?", fonte="Verdi", da_anno="100"),
        _row(riga_v0="4", tipo_riga="identità", sito_id="S02", sito="Porta", identita="porta di pietra",
             scala="edificio", da="?", a="300", tipo_cambio="fase della stessa unità funzionale (US diverse)",
             fonte="Verdi", a_anno="300"),
        _row(riga_v0="5", tipo_riga="UT", sito_id="S03", sito="Sito 9 (UT9)", identita="UT: coppi",
             da="2015", a="2015", fonte="schede UT", da_anno="2015", a_anno="2015"),
        _row(riga_v0="5", tipo_riga="identità", sito_id="S03", sito="Sito 9 (UT9)",
             identita="edificio di funzione non determinata (supposto)", scala="edificio?",
             da="romana (generica)", a="?", evidenza="simbolo: nessun membro; fonte la UT",
             fonte="schede UT"),
        _row(riga_v0="6", tipo_riga="lettura alternativa (o villa o fattoria)", sito_id="S01",
             sito="Colle", identita="fattoria", scala="edificio", fonte="Rossi 2000"),
        _row(riga_v0="7", tipo_riga="identità", sito_id="S01", sito="Colle", identita="cimitero",
             scala="complesso", tipo_cambio="dopo, sullo stesso sito (is_after), nessuna catena",
             fonte="Neri"),
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def test_the_import_of_a_synthetic_table(tmp_path):
    table = tmp_path / "lm.csv"
    _synthetic_table(table)
    container, report = import_landscape_matrix_csv(str(table), title="sintetico",
                                                    cited=[{"id": "X", "title": "studio"}])
    assert container.header["kind"] == "landscape"
    assert container.header["composition"] == [{"id": "X", "title": "studio"}]
    g = container.graphs["LANDSCAPE"]
    c = report["counts"]
    assert (c["sites"], c["functional_units"], c["topographic_units"]) == (3, 6, 1)
    assert (c["transformations"], c["is_after"], c["phases"], c["alternative_readings"]) == (1, 1, 2, 1)
    assert not [e for e in g.edges if e.edge_type == "generic_connection"]
    fus = {n.name: n for n in g.nodes if isinstance(n, FunctionalUnitNodeGroup)}
    # the two gates are ONE unit with two phases, its life from the first to the last
    gate = fus["Porta"]
    assert FU.life(g, gate.node_id) == (100, 300)
    assert gate.scale == "building"
    # the chain villa → castle
    t = FU.transformations(g)
    assert [(g.find_node_by_id(x["former"]).name, g.find_node_by_id(x["latter"]).name) for x in t] \
        == [("villa", "castello")]
    assert t[0]["transformation_kind"] == "reuse"
    # «oggi» leaves the end open: info, not a warning
    assert FU.life(g, fus["castello"].node_id) == (1100, None)
    assert any("oggi" in i for i in report["info"])
    # the supposed building: no members, its function extracted from the UT
    supposed = fus["edificio di funzione non determinata (supposto)"]
    assert supposed.scale is None and any("edificio?" in w for w in report["warnings"])
    pf = [e.edge_target for e in g.edges if e.edge_source == supposed.node_id and e.edge_type == "has_property"]
    ext = [e.edge_target for e in g.edges if e.edge_source in pf and e.edge_type == "has_data_provenance"]
    sources = {type(g.find_node_by_id(e.edge_target)).__name__ for e in g.edges
               if e.edge_source in ext and e.edge_type == "extracted_from"}
    assert sources == {"DocumentNode", "TopographicUnitNode"}
    assert FU.presence(g, supposed.node_id)["evidence"] == FU.SYMBOL
    # no invented date: undated, said
    assert FU.life(g, supposed.node_id) == (None, None)
    assert any("romana (generica)" in w for w in report["warnings"])
    assert "Date nella tabella" in supposed.description
    # the alternative reading is marked; the cemetery comes after the villa
    assert fus["fattoria"].data["alternative_reading"].startswith("lettura alternativa")
    after = [(g.find_node_by_id(e.edge_source).name, g.find_node_by_id(e.edge_target).name)
             for e in g.edges if e.edge_type == "is_after"]
    assert after == [("cimitero", "villa")]
    ut = [n for n in g.nodes if isinstance(n, TopographicUnitNode)][0]
    assert ut.name == "UT9" and FU.life(g, ut.node_id) == (2015, 2015)


@pytest.mark.skipif(not V1.exists(), reason="the Sarmizegetusa dataset is not on this machine")
def test_the_import_of_the_landscape_matrix_v1_of_sarmizegetusa():
    container, report = import_landscape_matrix_csv(str(V1), title="Sarmizegetusa")
    c = report["counts"]
    assert report["rows"] == 60
    assert c["sites"] == 25
    assert c["topographic_units"] == 9           # 5 UT rows + UT01, UT04, UT21, UT22
    assert c["functional_units"] == 47           # 55 rows − 5 UT − 7 phases + 4 merged… as counted
    assert c["phases"] == 11                      # walls 2, Porta Nord 4, forum 3, amphitheatre 2
    assert c["transformations"] == 17 and c["is_after"] == 1
    assert c["alternative_readings"] == 2
    assert report["unresolved_chains"] == []
    g = container.graphs["LANDSCAPE"]
    assert not [e for e in g.edges if e.edge_type == "generic_connection"]
    names = {n.data.get("row_v0"): n.name for n in g.nodes if isinstance(n, FunctionalUnitNodeGroup)}
    pairs = {(names[g.find_node_by_id(t["former"]).data["row_v0"]],
              names[g.find_node_by_id(t["latter"]).data["row_v0"]]) for t in FU.transformations(g)}
    assert ("tempio", "rudere") in pairs and ("rudere", "tempio restaurato: sito da visitare") in pairs
    assert ("Forum vetus (foro di Traiano)", names["20"]) in pairs
    # no invented dates: every missing bound is a warning
    assert sum(1 for w in report["warnings"] if w.startswith("[date]")) >= 60
