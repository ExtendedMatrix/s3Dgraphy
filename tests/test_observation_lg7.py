"""MICRO-LG7 §D (E.D., 22 Nov 2026) — the observation in a campaign, a datum of
its own: a dated PropertyNode ``observation`` (year, source in the paradata),
independent of the epochs, ALWAYS a lower bound of the end of the unit's life.
"""
from __future__ import annotations

import json

import pytest

from s3dgraphy import Graph
from s3dgraphy import observation as OBS
from s3dgraphy.container import Container, build_container, parse_container
from s3dgraphy.importer.unified_xlsx_importer import UnifiedXLSXImporter
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.stratigraphic_node import DocumentaryStratigraphicUnit, StratigraphicUnit



def _xlsx(path, docs, units, claims, epochs):
    """The sheet of tests/test_unit_life_lg3.py (same columns)."""
    from openpyxl import Workbook
    sheets = {
        "Units": (["ID", "TYPE", "NAME"], units),
        "Epochs": (["ID", "NAME", "START", "END", "COLOR"], epochs),
        "Claims": (["TARGET_ID", "TARGET2_ID", "PROPERTY_TYPE", "VALUE", "UNITS",
                    "COMBINER_REASONING", "EXTRACTOR_1", "SOURCE_1", "AUTHOR_1",
                    "AUTHOR_KIND_1"], claims),
        "Authors": (["ID", "KIND", "DISPLAY_NAME", "ORCID", "AFFILIATION"],
                    [["A.01", "author", "Jane Roe", "", ""]]),
        "Documents": (["ID", "FILENAME", "TITLE", "YEAR", "AUTHOR_IDS", "ROLE"], docs),
    }
    wb = Workbook()
    wb.remove(wb.active)
    for name, (headers, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(headers)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return str(path)


def _wall_case(tmp_path, br_end):
    """A US born in «Modern» (1900–2026), closed by a BR dated *br_end*, cited
    by the report of 2006 — a year inside the epoch that is ALREADY its own."""
    claims = [["W", "", "description", "the wall", "", "", "q", "R06", "A.01", "author"],
              ["W", "", "has_first_epoch", "E2", "", "", "q", "R06", "A.01", "author"],
              ["BR1", "W", "is_after", "", "", "", "q", "R06", "A.01", "author"],
              ["BR1", "", "absolute_time_end", str(br_end), "", "", "q", "R06", "A.01", "author"]]
    path = _xlsx(tmp_path / "em_data.xlsx",
                 docs=[["R06", "r06.pdf", "Report 2006", "2006", "A.01", "analytical"]],
                 units=[["W", "US", "wall"], ["BR1", "BR", "wall gone"]],
                 claims=claims,
                 epochs=[["E1", "Trajanic", 98, 117, ""], ["E2", "Moderna", 1900, 2026, ""]])
    imp = UnifiedXLSXImporter(path, graph_id="lg7-d")
    return imp, imp.parse()


def test_br_1990_cited_2006_in_an_epoch_already_its_own_now_warns(tmp_path):
    """The limit of LG3b: the epoch of 2006 was already the unit's, no edge,
    no bound, no warning. Now the observation is written and the BR of 1990
    contradicts it."""
    imp, g = _wall_case(tmp_path, 1990)
    w = next(n for n in g.nodes if n.name == "W")
    obs = OBS.observations(g, w.node_id)
    assert [(o["year"], g.find_node_by_id(o["documents"][0]).name) for o in obs] == [(2006.0, "R06")]
    assert imp.stats["observed_in_campaign"] == 1
    warnings = []
    iv = g.chronology(warnings=warnings)[w.node_id]
    assert iv["end"] == 1990.0 and iv["end_earliest"] == 2006.0
    assert any("[chronology window]" in x and "'W'" in x and "2006" in x for x in warnings)
    assert [(c["end"], c["year"]) for c in OBS.observation_conflicts(g)] == [(1990.0, 2006.0)]
    # no survive_in_epoch anywhere
    assert not [e for e in g.edges if e.edge_type == "survive_in_epoch"]
    # a BR after the document: no warning
    imp, g = _wall_case(tmp_path, 2010)
    warnings = []
    g.chronology(warnings=warnings)
    assert not any("[chronology window]" in x for x in warnings)
    assert OBS.observation_conflicts(g) == []


def test_the_record_and_its_paradata(tmp_path):
    imp, g = _wall_case(tmp_path, 2010)
    w = next(n for n in g.nodes if n.name == "W")
    (o,) = OBS.observations(g, w.node_id)
    p = g.find_node_by_id(o["property"])
    assert (p.name, p.property_type) == ("observation", "observation")
    assert p.data["valid_from"] == p.data["valid_to"] == 2006.0
    assert p.data["origin"] == "derived"
    (x,) = o["extractors"]
    ext = g.find_node_by_id(x)
    assert ext.node_type == "extractor" and "2006" in ext.description
    assert [e.edge_target for e in g.edges
            if e.edge_source == x and e.edge_type == "extracted_from"] == o["documents"]
    # a window of life, the year, source the property
    ws = g.chronology()[w.node_id]["windows"]
    assert [(v["start"], v["end"], v["rule"], v["relation"], v["document"]) for v in ws] == [
        (2006.0, 2006.0, "observed", "has_property", "R06")]


def _old_graph():
    g = Graph("LG3")
    g.add_node(EpochNode("C13", "Campaign 2013", 2013, 2013))
    g.add_node(EpochNode("MOD", "Modern", 1900, 2026))
    g.add_node(DocumentaryStratigraphicUnit("D", "USD01"))
    g.add_node(StratigraphicUnit("W", "US02"))
    g.add_node(DocumentNode("R13", "R13", description="r13.pdf | Report 2013 | 2013"))
    g.add_node(DocumentNode("R99", "R99", description="r99.pdf | Report"))
    e = g.add_edge("o1", "D", "C13", "survive_in_epoch")
    e.attributes.update({"origin": "derived", "rule": "observed_in_campaign", "document": "R13",
                         "year": 2013.0})
    e = g.add_edge("o2", "W", "MOD", "survive_in_epoch")            # LG3: no year on the edge
    e.attributes.update({"origin": "derived", "rule": "observed_in_campaign", "document": "R13"})
    e = g.add_edge("o3", "D", "MOD", "survive_in_epoch")            # no year anywhere
    e.attributes.update({"origin": "derived", "rule": "observed_in_campaign", "document": "R99"})
    g.add_edge("s1", "W", "C13", "survive_in_epoch")                # a plain survival: untouched
    return g


def test_the_old_edges_are_read_and_become_records():
    g = _old_graph()
    doc = build_container(Container(graphs={"LG3": g}, active_graph_id="LG3", header={"title": "t"}))
    again, warnings = parse_container(json.loads(json.dumps(doc)))
    back = again.graphs["LG3"]
    assert sum("[observation migration]" in w for w in warnings) == 1
    assert [e.edge_id for e in back.edges if e.edge_type == "survive_in_epoch"] == ["s1"]
    got = sorted(((u, o["year"], o["epoch"], back.find_node_by_id(o["documents"][0]).name)
                  for u in ("D", "W") for o in OBS.observations(back, u)),
                 key=lambda r: (r[0], r[1] or -1))
    # the year of the edge; the year of the document (its description); none: the epoch
    assert got == [("D", None, "MOD", "R99"), ("D", 2013.0, None, "R13"), ("W", 2013.0, None, "R13")]
    ws = back.chronology()["D"]["windows"]
    assert sorted((w["start"], w["end"]) for w in ws) == [(1900.0, 2026.0), (2013.0, 2013.0)]
    # the next save writes the records only; idempotent
    out = json.dumps(build_container(again))
    assert "observed_in_campaign" in out            # the rule stays in the record's data
    assert '"rule": "observed_in_campaign", "document"' not in out
    assert OBS.migrate_observed_in_campaign(back)["migrated"] == 0


def test_the_datamodel_says_it():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
    q = json.loads((root / "em_qualia_types.json").read_text(encoding="utf-8"))
    spec = q["property_names"]["observation"]
    assert "INDEPENDENT OF THE EPOCHS" in spec["description"]
    assert spec["rdf"]["class"] == "crmsci:S4_Observation"
    assert spec["rdf"]["from_unit"] == "crmsci:O8i_was_observed_by"
    from s3dgraphy.tools import datamodel_i18n as I
    assert I.translate("property_names", "observation", "label", "it") == "Osservazione"


def test_rdf_the_observation_is_an_s4_with_its_year(tmp_path):
    rdflib = pytest.importorskip("rdflib")
    from rdflib import Namespace, RDF, Literal
    from s3dgraphy.exporter.rdf_exporter import RDFExporter
    g = _old_graph()
    OBS.migrate_observed_in_campaign(g)
    path = tmp_path / "lg7.ttl"
    RDFExporter(str(path), format="turtle").export_single_graph(g)
    store = rdflib.Graph()
    store.parse(str(path), format="turtle")
    CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
    SCI = Namespace("http://www.cidoc-crm.org/extensions/crmsci/")
    obs = set(store.subjects(RDF.type, SCI.S4_Observation))
    assert len(obs) == 3
    w_iri = next(s for s in store.subjects(RDF.type, None) if str(s).endswith("/node/W"))
    (o,) = list(store.objects(w_iri, SCI.O8i_was_observed_by))
    ts = next(store.objects(o, CRM["P4_has_time-span"]))
    assert (ts, CRM.P82a_begin_of_the_begin, Literal(2013.0)) in store
    assert (ts, CRM.P82b_end_of_the_end, Literal(2013.0)) in store
