"""The em.json conformance suite, read and written by s3Dgraphy.

MICRO specifica em.json, part 4 (24 Oct 2026). The samples and their expected
results live in ``spec/em-json/conformance/`` beside the specification; the
expected result is the REFERENCE READING (``reference_reading.py``, standard
library only), not s3Dgraphy's. Here s3Dgraphy is held to it:

* every sample validates against the schema of its form;
* s3Dgraphy reads every sample to the expected result (it may add the default
  geo-position node of a graph, nothing else);
* read → write → read loses nothing the specification describes: every node
  with its type, name, description and data, every edge with its attributes,
  every link, the roles of the members, the active graph, the header keys a
  writer does not own; and what it writes validates against em.v1.1;
* what s3Dgraphy exports — a fresh graph, a GraphML import, the old fixtures
  re-saved — validates against em.v1.1 and says ``"version": "1.1"``.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from s3dgraphy.container import build_container, container_of, parse_container
from s3dgraphy.exporter.emjson_exporter import FORMAT_VERSION

jsonschema = pytest.importorskip("jsonschema")

SPEC = Path(__file__).resolve().parents[1] / "spec" / "em-json"
SUITE = SPEC / "conformance"
SAMPLES = sorted(SUITE.glob("*.em.json"))
FIXTURES = Path(__file__).parent / "fixtures"


def _validator(name):
    return jsonschema.Draft202012Validator(
        json.loads((SPEC / name).read_text(encoding="utf-8")))


V11 = _validator("em.v1.1.schema.json")


def _expected(sample):
    return json.loads((SUITE / "expected" / (sample.name[:-len(".em.json")] + ".json"))
                      .read_text(encoding="utf-8"))


def _reading(container):
    """s3Dgraphy's reading, in the shape of the reference reading."""
    def section(graph, role):
        return {
            "role": role,
            "nodes": {n.node_id: n.node_type for n in graph.nodes},
            "edges": {e.edge_id: [e.edge_type, e.edge_source, e.edge_target]
                      for e in graph.edges},
            "links": {l["id"]: [l["edge_type"], l["source"],
                                l["target"]["graph_id"], l["target"]["node_id"]]
                      for l in (getattr(graph, "links", None) or [])},
        }
    graphs = {gid: section(g, "study") for gid, g in container.graphs.items()}
    for attr, role in (("shelf", "shelf"), ("corpus", "dtc"),
                       ("periodizations", "periodizations")):
        g = getattr(container, attr, None)
        if g is not None:
            graphs[g.graph_id] = section(g, role)
    return {"active_graph_id": container.active_graph_id, "graphs": graphs}


def _assert_reads_as_expected(got, want):
    assert got["active_graph_id"] == want["active_graph_id"]
    assert set(got["graphs"]) == set(want["graphs"])
    for gid, w in want["graphs"].items():
        g = got["graphs"][gid]
        assert g["role"] == w["role"], gid
        extra = {i: t for i, t in g["nodes"].items() if i not in w["nodes"]}
        assert {i: g["nodes"].get(i) for i in w["nodes"]} == w["nodes"], gid
        # the one addition allowed: the default geo-position of the graph
        assert all(t == "geo_position" for t in extra.values()), (gid, extra)
        assert g["edges"] == w["edges"], gid
        assert g["links"] == w["links"], gid


def _sections(doc):
    if isinstance(doc.get("graphs"), dict):
        return {str(s.get("graph_id") or k): s for k, s in doc["graphs"].items()}
    return {str(doc["graph"].get("graph_id")): doc["graph"]}


def _dig(doc, path):
    cur = doc
    for i, step in enumerate(path):
        if i == 1 and path[0] == "graphs":
            cur = _sections(doc)[step]
        elif isinstance(cur, dict) and step in ("nodes", "edges") and i == 2:
            cur = {x["id"]: x for x in cur[step]}
        else:
            cur = cur[step]
    return cur


def test_the_expected_results_are_the_reference_reading():
    spec = importlib.util.spec_from_file_location("reference_reading",
                                                  SUITE / "reference_reading.py")
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    for sample in SAMPLES:
        assert ref.expected_for(sample) == _expected(sample), sample.name


def test_the_suite_holds_the_six_cases():
    assert [s.name[:2] for s in SAMPLES] == ["01", "02", "03", "04", "05", "06"]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.name)
def test_every_sample_validates_against_its_schema(sample):
    doc = json.loads(sample.read_text(encoding="utf-8"))
    errors = list(_validator(_expected(sample)["schema"]).iter_errors(doc))
    assert not errors, [e.message for e in errors]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.name)
def test_s3dgraphy_reads_every_sample_as_expected(sample):
    container, _warnings = parse_container(json.loads(sample.read_text(encoding="utf-8")))
    _assert_reads_as_expected(_reading(container), _expected(sample))


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: p.name)
def test_the_round_trip_loses_nothing(sample):
    source = json.loads(sample.read_text(encoding="utf-8"))
    container, _ = parse_container(source)
    written = json.loads(json.dumps(build_container(container)))
    errors = list(V11.iter_errors(written))
    assert not errors, [e.message for e in errors]
    assert written["header"]["version"] == FORMAT_VERSION == "1.1"
    back, _ = parse_container(written)
    _assert_reads_as_expected(_reading(back), _expected(sample))
    # every node and edge with its content, as written in the sample
    out = _sections(written)
    for gid, section in _sections(source).items():
        nodes = {n["id"]: n for n in out[gid]["nodes"]}
        for n in section.get("nodes") or []:
            m = nodes[n["id"]]
            for key in ("node_type", "name", "description"):
                if n.get(key):
                    assert m.get(key) == n[key], (gid, n["id"], key)
            for key, value in (n.get("data") or {}).items():
                assert (m.get("data") or {}).get(key) == value, (gid, n["id"], key)
        edges = {e["id"]: e for e in out[gid]["edges"]}
        for e in section.get("edges") or []:
            assert {k: edges[e["id"]][k] for k in ("edge_type", "source", "target")} == \
                {k: e[k] for k in ("edge_type", "source", "target")}
            for key, value in (e.get("attributes") or {}).items():
                assert edges[e["id"]].get("attributes", {}).get(key) == value
        if section.get("layout"):
            assert out[gid].get("layout") == section["layout"], gid
    for path in _expected(sample)["must_survive_round_trip"]:
        assert _dig(written, path) == _dig(source, path), path


def test_s3dgraphy_never_writes_an_extension_key():
    """§6: the official tools never write `x-` keys of their own."""
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    for sample in SAMPLES[:5]:                      # the samples without x- keys
        container, _ = parse_container(json.loads(sample.read_text(encoding="utf-8")))
        assert not [k for k in keys(build_container(container)) if k.startswith("x-")]


def _exports():
    from s3dgraphy.graph import Graph
    from s3dgraphy.importer.import_graphml import GraphMLImporter
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g = Graph("fresh")
    for uid in ("US1", "US2"):
        g.add_node(StratigraphicUnit(uid, uid))
    g.add_edge("e", "US1", "US2", "abuts")
    yield "a fresh graph", build_container(container_of(g))
    imported = GraphMLImporter(str(FIXTURES / "epochs_partial_dates.graphml"),
                               Graph("gml")).parse()
    yield "a GraphML import", build_container(container_of(imported))
    for name in ("TempluMare.em.json", "PortaMarina-lite.em.json",
                 "vitruvio/vitruvio.em.json"):
        c, _ = parse_container(json.loads((FIXTURES / name).read_text(encoding="utf-8")))
        yield f"{name} re-saved", build_container(c)


def test_every_export_validates_against_em_v1_1():
    for what, doc in _exports():
        doc = json.loads(json.dumps(doc))
        errors = list(V11.iter_errors(doc))
        assert not errors, (what, [e.message for e in errors][:3])
        assert doc["header"]["version"] == "1.1", what
