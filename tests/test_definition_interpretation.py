"""definition → interpretation (MICRO-J §C, E.D. 17 Nov 2026).

Three entries, two texts: the description (what is seen), the interpretation (a
PropertyNode with its chain), the definition (the element data.definition, a
term). The PropertyNode `definition` of the EM 1.5 templates is the historical
spelling of `interpretation`: readable as its alias, imported as interpretation,
renamed in place by a migration that keeps the ids."""
import copy
import json
import pathlib

import pytest

from s3dgraphy.migrations import definition_to_interpretation as d2i
from s3dgraphy.tools import datamodel_i18n as t

CFG = pathlib.Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config"
FIXTURE = pathlib.Path(__file__).parent / "sync" / "fixtures" / "mini_volterra_baseline_ai03.graphml"


def _section():
    return {"nodes": [
        {"id": "u1", "node_type": "US", "name": "SU001", "data": {}},
        {"id": "u2", "node_type": "US", "name": "SU002", "data": {}},
        {"id": "p1", "node_type": "property", "name": "definition",
         "description": "Foundation of the temple's podium",
         "data": {"property_type": "definition", "value": "Foundation of the temple's podium"}},
        {"id": "p2", "node_type": "property", "name": "definition", "description": "crollo",
         "data": {"property_type": "definition", "value": "crollo"}},
        {"id": "p3", "node_type": "property", "name": "material", "description": "tufo",
         "data": {"property_type": "material"}},
        {"id": "x1", "node_type": "extractor", "name": "D.01.01", "data": {}},
        {"id": "d1", "node_type": "document", "name": "D.01", "data": {}},
    ], "edges": [
        {"id": "e1", "source": "u1", "target": "p1", "edge_type": "has_property"},
        {"id": "e2", "source": "u2", "target": "p2", "edge_type": "has_property"},
        {"id": "e3", "source": "u1", "target": "p3", "edge_type": "has_property"},
        {"id": "e4", "source": "p1", "target": "x1", "edge_type": "has_data_provenance"},
        {"id": "e5", "source": "x1", "target": "d1", "edge_type": "extracted_from"},
    ]}


def test_the_datamodel_says_the_rule():
    q = json.loads((CFG / "em_qualia_types.json").read_text(encoding="utf-8"))
    names = q["property_names"]
    assert names["definition"]["alias_of"] == "interpretation"
    assert "interpretation" in names and "_rule" in names
    assert "data.definition" in names["_rule"] and "em-us-definizione" in names["_rule"]
    t._doc.cache_clear()
    assert t.property_name_label("interpretation", "it") == "Interpretazione"
    # the historical name stays readable
    assert t.property_name_label("definition", "it") == "Definizione"


def test_the_plan_says_unit_value_chain_and_what_looks_like_a_term():
    rows = d2i.plan_emjson(_section(), terms={"crollo": "https://w3id.org/extendedmatrix/vocab/us-definizione/crollo"})
    assert [r["node_id"] for r in rows] == ["p1", "p2"]
    p1, p2 = rows
    assert p1["units"][0]["name"] == "SU001" and p1["suggestion"] == "interpretation"
    assert [c["name"] for c in p1["chain"]] == ["D.01.01", "D.01"]
    assert p2["suggestion"] == "term" and p2["looks_like_term"].endswith("/crollo")


def test_the_delta_renames_in_place_and_its_undo_puts_it_back():
    section = _section()
    before = copy.deepcopy(section)
    ops = d2i.delta(d2i.plan_emjson(section), keep=["p2"])
    assert {o["node_id"] for o in ops} == {"p1"} and {o["field"] for o in ops} == {"name", "data.property_type"}
    assert d2i.apply_emjson(section, ops) == 1
    p1 = next(n for n in section["nodes"] if n["id"] == "p1")
    assert (p1["name"], p1["data"]["property_type"]) == ("interpretation", "interpretation")
    assert p1["description"] == "Foundation of the temple's podium"
    assert [e["id"] for e in section["edges"]] == [e["id"] for e in before["edges"]]
    d2i.apply_emjson(section, d2i.undo_delta(ops))
    p1 = next(n for n in section["nodes"] if n["id"] == "p1")
    assert (p1["name"], p1["data"]["property_type"]) == ("definition", "definition")


def test_the_graphml_importer_reads_definition_as_interpretation(tmp_path):
    from s3dgraphy.graph import Graph
    from s3dgraphy.importer.import_graphml import GraphMLImporter
    src = FIXTURE.read_text(encoding="utf-8").replace(">Interpretation<", ">definition<")
    assert ">definition<" in src
    path = tmp_path / "em15.graphml"
    path.write_text(src, encoding="utf-8")
    g = Graph(graph_id="em15")
    imp = GraphMLImporter(str(path), g)
    imp.parse()
    props = [n for n in g.nodes if n.node_type == "property"]
    assert props and all(n.name == "interpretation" for n in props)
    assert sorted(imp.renamed_definitions) == sorted(n.node_id for n in props)
    # same ids as the file says, the edges still reach them
    ids = {n.node_id for n in props}
    assert any(e.edge_target in ids and e.edge_type == "has_property" for e in g.edges)
    assert d2i.plan(g) == []
