"""The persons of a pyArchInit sheet (MICRO ruoli persone, 27 Nov 2026,
decisions of E.D.): FIRST THE ACTS, then the roles only for what is missing.

- a person is the author of an ACT of the unit's documentation — an
  ActivityNodeGroup with ``data.act_kind`` (em-documentation-act), the unit
  ``is_in_activity`` of it, the act ``has_author`` the person;
- ``schedatore`` → the recording act (one per unit), ``direttore_us`` → the
  excavation act (shared by site, year and director), ``responsabile_us`` →
  the revision act (pyArchInit's own sheet: «Responsabile rielaborazione»);
- a role the act does not say is ``attributes.role`` on that ``has_author``
  (connections 1.6.62, scheme em-person-role); in RDF P14 carried out by and
  P14.1 in the role of (PC14);
- the way back writes the three columns from the graph.
"""
from __future__ import annotations

import copy
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.sync.graph_ingestor import GraphIngestor, MAPPED_COLUMNS
from s3dgraphy.sync.graph_projector import GraphProjector
from s3dgraphy.unit_row import RowReader, person_columns

FIXTURES = Path(__file__).parent / "fixtures"
SITO = "TestSite"
PERSONS = ("schedatore", "direttore_us", "responsabile_us")

#: Anna is the recorder of US1 and US2 and the reviser of US3; Marco directs
#: 2012 (US1-3), Carla 2013 (US4-5).
ROWS = {
    "1": ("Anna Rossi", "Marco Bianchi", "Luigi Verdi", 2012),
    "2": ("Anna Rossi", "Marco Bianchi", "Luigi Verdi", 2012),
    "3": ("Luigi Verdi", "Marco Bianchi", "Anna Rossi", 2012),
    "4": ("Luigi Verdi", "Carla Neri", "", 2013),
    "5": ("", "Carla Neri", "Luigi Verdi", 2013),
}


def _db(tmp_path, name="mv.sqlite"):
    db = tmp_path / name
    shutil.copy2(FIXTURES / "mini_volterra.sqlite", db)
    con = sqlite3.connect(db)
    for us, (sch, dire, resp, anno) in ROWS.items():
        con.execute("UPDATE us_table SET schedatore=?, direttore_us=?, "
                    "responsabile_us=?, anno_scavo=? WHERE us=?",
                    (sch, dire, resp, anno, us))
    con.commit()
    con.close()
    from tests.sync._uuid_backfill import add_columns, backfill_uuids
    add_columns(db)
    backfill_uuids(db)
    return db


def _cols(db):
    con = sqlite3.connect(db)
    out = {str(r[0]): tuple((v or "") for v in r[1:]) for r in con.execute(
        f"SELECT us, {', '.join(PERSONS)} FROM us_table WHERE sito=?", (SITO,))}
    con.close()
    return out


def _insert_back(graph, db, tmp_path, name="ins.sqlite"):
    ins = tmp_path / name
    shutil.copy2(db, ins)
    con = sqlite3.connect(ins)
    con.execute("DELETE FROM us_table WHERE sito=?", (SITO,))
    con.commit()
    con.close()
    GraphIngestor().populate_list(graph, ins, sito=SITO, dry_run=False)
    return ins


def _via_emjson(graph):
    doc = json.loads(json.dumps(build_emjson(graph)))
    g2, _w = parse_emjson(doc)
    return doc, g2


def _unit(graph, us):
    from s3dgraphy.rapporti import us_number_of
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicNode
    return next(n for n in graph.nodes
                if isinstance(n, StratigraphicNode) and str(us_number_of(n)) == str(us))


def _acts_of(graph, node):
    by = {n.node_id: n for n in graph.nodes}
    return [by[e.edge_target] for e in graph.edges
            if e.edge_source == node.node_id and e.edge_type == "is_in_activity"]


def _authors(graph, act):
    by = {n.node_id: n for n in graph.nodes}
    return [(by[e.edge_target].name, (e.attributes or {}).get("role"))
            for e in graph.edges
            if e.edge_source == act.node_id and e.edge_type == "has_author"]


# --------------------------------------------------------------- the acts

def test_a_person_is_the_author_of_an_act_not_of_the_unit(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    us1 = _unit(graph, 1)
    # no has_author out of a unit any more
    assert not [e for e in graph.edges if e.edge_type == "has_author"
                and e.edge_source == us1.node_id]
    acts = {a.data["act_kind"]: a for a in _acts_of(graph, us1)}
    assert set(acts) == {"recording", "excavation", "revision"}
    assert _authors(graph, acts["recording"]) == [("Anna Rossi", None)]
    assert _authors(graph, acts["excavation"]) == [("Marco Bianchi", None)]
    assert _authors(graph, acts["revision"]) == [("Luigi Verdi", None)]
    assert acts["excavation"].data["act_start"] == 2012
    # one person, one node
    assert sum(1 for n in graph.nodes if getattr(n, "name", "") == "Anna Rossi") == 1


def test_the_excavation_act_is_shared_by_site_year_and_director(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    exc = {us: next(a for a in _acts_of(graph, _unit(graph, us))
                    if a.data["act_kind"] == "excavation").node_id
           for us in ROWS}
    assert exc["1"] == exc["2"] == exc["3"]
    assert exc["4"] == exc["5"] != exc["1"]
    per_unit = [a.node_id for a in _acts_of(graph, _unit(graph, 1))
                if a.data["act_kind"] == "recording"]
    assert per_unit == [a.node_id for a in _acts_of(graph, _unit(graph, 1))
                        if a.data["act_kind"] == "recording"]
    assert per_unit[0] != next(a.node_id for a in _acts_of(graph, _unit(graph, 2))
                               if a.data["act_kind"] == "recording")


def test_one_person_two_roles_on_two_units_is_right_on_each(tmp_path):
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    reader = RowReader(graph)
    assert reader.persons(_unit(graph, 1)) == {
        "schedatore": "Anna Rossi", "direttore_us": "Marco Bianchi",
        "responsabile_us": "Luigi Verdi"}
    assert reader.persons(_unit(graph, 3)) == {
        "schedatore": "Luigi Verdi", "direttore_us": "Marco Bianchi",
        "responsabile_us": "Anna Rossi"}
    # until mapping 1.6.6 the role was the person's description, the first met
    anna = next(n for n in graph.nodes if getattr(n, "name", "") == "Anna Rossi")
    assert "compiler" not in (anna.description or "")


# ------------------------------------------------------------ the way back

def test_the_three_columns_come_back_from_the_graph(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    _doc, g2 = _via_emjson(graph)
    for col in PERSONS:
        assert col in MAPPED_COLUMNS
    ins = _insert_back(g2, db, tmp_path)
    assert _cols(ins) == _cols(db)


def test_an_update_writes_a_changed_person_back(tmp_path):
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    marco = next(n for n in graph.nodes if getattr(n, "name", "") == "Marco Bianchi")
    marco.name = "Marco Bianchi Jr."
    GraphIngestor().populate_list(graph, db, sito=SITO, dry_run=False)
    assert {us: c[1] for us, c in _cols(db).items()} == {
        "1": "Marco Bianchi Jr.", "2": "Marco Bianchi Jr.",
        "3": "Marco Bianchi Jr.", "4": "Carla Neri", "5": "Carla Neri"}


# ------------------------------------------------------ the role on the edge

@pytest.fixture
def supervisor_mapping(monkeypatch):
    """A column whose person holds a ROLE the act does not say (act_kind
    recording + person_role sector_supervisor, as iDAI.field's processor
    would map): the way of the role on the edge. responsabile_us itself is
    the revision act (confirmed by E.D., 27 Nov 2026)."""
    from s3dgraphy.mappings import mapping_registry
    real = mapping_registry.load_mapping

    def load(name, mtype):
        m = real(name, mtype)
        if name == "pyarchinit_us_mapping" and m:
            m = copy.deepcopy(m)
            m["column_mappings"]["responsabile_us"].update(
                act_kind="recording", person_role="sector_supervisor")
        return m
    monkeypatch.setattr(mapping_registry, "load_mapping", load)
    return load


def test_the_role_goes_on_the_edge_and_comes_back(tmp_path, supervisor_mapping):
    assert person_columns()["responsabile_us"] == ("recording", "sector_supervisor")
    db = _db(tmp_path)
    graph = GraphProjector().populate_graph(db, sito=SITO)
    rec = next(a for a in _acts_of(graph, _unit(graph, 3))
               if a.data["act_kind"] == "recording")
    assert sorted(_authors(graph, rec), key=str) == sorted(
        [("Luigi Verdi", None), ("Anna Rossi", "sector_supervisor")], key=str)
    doc, g2 = _via_emjson(graph)
    roles = [e.get("attributes") for e in doc["graph"]["edges"]
             if (e.get("attributes") or {}).get("role")]
    assert roles and all(r == {"role": "sector_supervisor"} for r in roles)
    ins = _insert_back(g2, db, tmp_path)
    assert _cols(ins) == _cols(db)


def test_the_role_is_p14_1_in_rdf(tmp_path, supervisor_mapping):
    rdflib = pytest.importorskip("rdflib")
    from s3dgraphy.exporter.rdf_exporter import export_single_graph_to_rdf
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    out = tmp_path / "g.ttl"
    export_single_graph_to_rdf(graph, str(out))
    g = rdflib.Graph().parse(out, format="turtle")
    CRM = rdflib.Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    role = rdflib.URIRef("https://w3id.org/extendedmatrix/vocab/person-role/sector_supervisor")
    pcs = list(g.subjects(rdflib.RDF.type, CRM.PC14_carried_out_by))
    assert pcs, "no PC14"
    for pc in pcs:
        assert (pc, CRM["P14.1_in_the_role_of"], role) in g
        act, person = g.value(pc, CRM.P01_has_domain), g.value(pc, CRM.P02_has_range)
        assert (act, CRM.P14_carried_out_by, person) in g
    assert (role, rdflib.RDF.type, CRM.E55_Type) in g
    # every author of an act is P14, with or without a role
    assert len(list(g.triples((None, CRM.P14_carried_out_by, None)))) > len(pcs)


# ----------------------------------------------------------- the datamodel

def test_has_author_declares_its_role():
    import s3dgraphy
    path = (Path(s3dgraphy.__file__).parent / "JSON_config"
            / "s3Dgraphy_connections_datamodel.json")
    dm = json.loads(path.read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_connections_model_version"] == "1.6.62"
    ha = dm["edge_types"]["has_author"]
    role = ha["attributes"]["role"]
    assert role["scheme"] == "em-person-role" and role["required"] is False
    assert "sector_supervisor" in role["values"]
    assert "P14.1_in_the_role_of" in ha["mapping"]["_act_comment"]


def test_the_mapping_says_the_acts():
    assert person_columns() == {"schedatore": ("recording", None),
                                "direttore_us": ("excavation", None),
                                "responsabile_us": ("revision", None)}


# ------------------------------------------------------------- the GraphML

def test_an_act_is_not_a_box_in_graphml(tmp_path):
    from s3dgraphy.exporter.graphml.graphml_exporter import GraphMLExporter
    graph = GraphProjector().populate_graph(_db(tmp_path), sito=SITO)
    out = tmp_path / "g.graphml"
    GraphMLExporter(graph).export(str(out))
    text = out.read_text(encoding="utf-8")
    assert ">recording " not in text and ">excavation " not in text
