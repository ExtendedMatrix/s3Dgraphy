"""MICRO-T-COLORI-NEL-FILE (E.D., 18 Nov 2026): the colour schemes inside the
em.json, in the ``presentation`` section — read, written, expelled to .emc and
imported back, cleaned; a file without it as before; the digest blind to it."""
import json
import os

import pytest

from s3dgraphy import presentation as P
from s3dgraphy.color_schemes import emc_document
from s3dgraphy.container import (Container, build_container, content_digest,
                                 load_container_file, parse_container,
                                 save_container_file)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _graph(gid="g1"):
    g = Graph(graph_id=gid)
    g.add_node(StratigraphicUnit(node_id=f"{gid}-us1", name="US1"))
    return g


def _scheme(prop="material", colours=None, **extra):
    return emc_document(prop, colours or {"white rock": "#00AA00",
                                          f"empty property {prop} node": "#FF00FF",
                                          f"no property {prop} node": "#BABABA"},
                        "TempluMare_v10", extra=extra or None)


def test_a_file_without_the_section_reads_and_writes_as_before(tmp_path):
    c = Container(graphs={"g1": _graph()}, active_graph_id="g1")
    doc = build_container(c)
    assert P.PRESENTATION_KEY not in doc
    back, warnings = parse_container(doc)
    assert back.presentation == P.empty() and not warnings
    assert P.PRESENTATION_KEY not in build_container(back)


def test_saved_and_opened_back_identical_and_the_digest_does_not_see_it(tmp_path):
    pres = P.empty()
    name = P.add_scheme(pres, "material", _scheme())
    P.set_active(pres, "g1", name)
    c = Container(graphs={"g1": _graph()}, active_graph_id="g1", presentation=pres)
    path = tmp_path / "a.em.json"
    save_container_file(c, str(path), bump=False)
    first = path.read_bytes()
    back, warnings = load_container_file(str(path))
    assert not warnings
    assert back.presentation[P.ACTIVE_KEY] == {"g1": "material"}
    save_container_file(back, str(path), bump=False)
    assert path.read_bytes() == first
    doc = json.loads(first)
    assert list(doc[P.PRESENTATION_KEY]) == [P.ACTIVE_KEY, P.SCHEMES_KEY]
    plain = {k: v for k, v in doc.items() if k != P.PRESENTATION_KEY}
    assert content_digest(doc) == content_digest(plain)


def test_expel_import_expel_identical_to_the_byte(tmp_path):
    pres = P.empty()
    P.add_scheme(pres, "material", _scheme())
    P.add_scheme(pres, "period/phase", _scheme("phase", {"1": "#440154", "2": "#FDE725"}))
    out = P.expel(pres, str(tmp_path / "a"))
    assert sorted(os.path.basename(p) for p in out) == ["material.emc", "period_phase.emc"]
    other = P.empty()
    names = P.import_emc_files(other, out)
    assert names == ["material", "period_phase"]
    again = P.expel(other, str(tmp_path / "b"))
    for a, b in zip(sorted(out), sorted(again)):
        assert open(a, "rb").read() == open(b, "rb").read()
    # an imported .emc is EM Tools' file: its reader takes it as it is
    doc = json.load(open(out[0], encoding="utf-8"))
    assert doc["metadata"]["property_name"] == "material"
    assert set(doc["color_mapping"]) == {"white rock", "empty property material node",
                                          "no property material node"}


def test_import_keeps_both_when_names_meet():
    pres = P.empty()
    assert P.add_scheme(pres, "material", _scheme()) == "material"
    assert P.add_scheme(pres, "material", _scheme()) == "material (2)"
    assert P.scheme_names(pres) == ["material", "material (2)"]


def test_clean_says_what_it_takes_and_gives_it_back():
    pres = P.empty()
    P.add_scheme(pres, "material", _scheme())
    P.add_scheme(pres, "phase", _scheme("phase", {"1": "#440154"}))
    P.set_active(pres, "g1", "material")
    P.set_active(pres, "g2", "material")
    assert P.summary(pres) == {"schemes": 2, "active": 1}
    before = P.clean(pres)
    assert P.section(pres) is None
    pres.update(before)
    assert P.summary(pres) == {"schemes": 2, "active": 1}


def test_removing_a_scheme_frees_the_graphs_that_used_it():
    pres = P.empty()
    P.add_scheme(pres, "material", _scheme())
    P.set_active(pres, "g1", "material")
    assert P.remove_scheme(pres, "material")
    assert pres[P.ACTIVE_KEY] == {}
    with pytest.raises(KeyError):
        P.set_active(pres, "g1", "material")


def test_what_cannot_be_read_is_left_out_and_said():
    doc = {"graphs": {"g1": {"nodes": [], "edges": []}},
           P.PRESENTATION_KEY: {
               P.SCHEMES_KEY: {"ok": _scheme(), "bad": {"metadata": {}},
                               "nan": {"metadata": {"property_name": "p"},
                                       "color_mapping": {"a": ["x", 0, 0]}}},
               P.ACTIVE_KEY: {"g1": "bad", "g2": "ok"}}}
    pres, warnings = P.read_presentation(doc)
    assert P.scheme_names(pres) == ["ok"]
    assert pres[P.ACTIVE_KEY] == {"g2": "ok"}
    assert len(warnings) == 3
    assert P.read_presentation({P.PRESENTATION_KEY: []})[1]


def test_a_colour_is_bound_to_the_code_of_the_value_when_there_is_one():
    aat = "http://vocab.getty.edu/aat/300011176"
    sch = _scheme(value_codes={"white rock": aat})
    # the same term in Italian: its code finds the colour
    got = P.colours_for_values(sch, {"pietra bianca": aat, "white rock": None,
                                     "marble": None, "other": "http://x/1"})
    assert got == {"pietra bianca": "#00AA00", "white rock": "#00AA00"}
    # a code the scheme does not know falls back to the text
    assert P.colours_for_values(sch, {"white rock": "http://x/2"}) == {"white rock": "#00AA00"}


def test_merging_another_files_schemes():
    a, b = P.empty(), P.empty()
    P.add_scheme(a, "material", _scheme())
    P.add_scheme(b, "material", _scheme())
    P.add_scheme(b, "phase", _scheme("phase", {"1": "#440154"}))
    P.set_active(b, "g9", "phase")
    P.add_scheme(b, "other", _scheme(colours={"stone": "#123456"}))
    renamed = P.merge(a, b)
    assert renamed == {"material": "material", "other": "other", "phase": "phase"}
    assert a[P.ACTIVE_KEY] == {"g9": "phase"}
    c = P.empty()
    P.add_scheme(c, "material", _scheme(colours={"stone": "#000000"}))
    assert P.merge(a, c) == {"material": "material (2)"}


def test_the_multigraph_manager_keeps_the_schemes_on_save(tmp_path):
    from s3dgraphy.multigraph.multigraph import MultiGraphManager
    pres = P.empty()
    P.add_scheme(pres, "material", _scheme())
    P.set_active(pres, "g1", "material")
    src = tmp_path / "in.em.json"
    save_container_file(Container(graphs={"g1": _graph()}, active_graph_id="g1",
                                  presentation=pres), str(src), bump=False)
    m = MultiGraphManager()
    m.load_container(str(src), replace=True)
    out = tmp_path / "out.em.json"
    m.save_container(str(out))
    assert json.loads(out.read_text())[P.PRESENTATION_KEY] == json.loads(src.read_text())[P.PRESENTATION_KEY]


def test_a_file_with_the_section_still_validates_against_the_1_1_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "spec", "em-json", "em.v1.1.schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)
    pres = P.empty()
    P.add_scheme(pres, "material", _scheme())
    P.set_active(pres, "g1", "material")
    doc = build_container(Container(graphs={"g1": _graph()}, active_graph_id="g1", presentation=pres))
    jsonschema.Draft202012Validator(schema).validate(json.loads(json.dumps(doc)))
