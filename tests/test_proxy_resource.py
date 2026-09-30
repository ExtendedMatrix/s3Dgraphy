"""The proxy reaches its .glb through a RESOURCE (connections 1.6.28).

E.D. 2026-09-30: the proxy is a property of the US, and its glb is a
``proxy_model`` resource. The shape reaches it the way a Representation Model
reaches its bytes::

    US ─has_property→ Property(geometry) ─has_semantic_shape→ SemanticShape
                                                   └─has_linked_resource→ ResourceNode(proxy_model)

What is defended:

* ``create_geometry_proxy`` writes the resource, never the shape's ``url``;
* an old graph whose shape carries a ``url`` opens with the resource, and a
  second open does not duplicate it;
* the form EMtools still writes (US ─has_semantic_shape→ shape with
  ``url = proxies/<US>.glb``) is migrated through both steps;
* a resource EMtools' Heriverse export already hangs off the shape with the
  same path is REUSED, not doubled;
* ``store_backed_geometry`` lists a resident proxy, bound to its unit;
* the RDF round-trip stays isomorphic, with the P67 of the resource;
* Heriverse still finds the path where it looks for it.
"""

import json

import rdflib
from rdflib.compare import isomorphic

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.exporter.rdf_exporter import CRM
from s3dgraphy.geometry import (PROXY_RESOURCE_TYPE, create_geometry_proxy,
                                proxy_resource_id, store_backed_geometry)
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.importer.rdf_importer import RDFImporter
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.semantic_shape_node import SemanticShapeNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _studio():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="US1"))
    return g


def _triples(g):
    return {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}


def _resources(g):
    return [n for n in g.nodes if n.node_type == "resource"]


def _reopen(g):
    doc = json.loads(json.dumps(build_emjson(g)))
    back, warnings = parse_emjson(doc)
    return back, warnings


# ── writing ─────────────────────────────────────────────────────────────────

def test_create_geometry_proxy_writes_the_resource_not_the_url():
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb"})
    shape = g.find_node_by_id(r.shape_id)
    assert shape.url == "" and "url" not in shape.data
    res = g.find_node_by_id(r.resource_id)
    assert r.resource_id == proxy_resource_id(r.shape_id)
    assert res.data["url"] == "proxies/US1.glb"
    assert res.data["url_type"] == PROXY_RESOURCE_TYPE
    assert (r.shape_id, "has_linked_resource", r.resource_id) in _triples(g)
    assert not r.warnings, r.warnings
    # idempotent: a re-send is the same nodes
    n, e = len(g.nodes), len(g.edges)
    create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb"})
    assert (len(g.nodes), len(g.edges)) == (n, e)


def test_hulls_and_spheres_ask_for_no_resource():
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]],
                                         "spheres": [[0, 0, 0, 0.5]]})
    assert r.resource_id is None
    assert not _resources(g)
    shape = g.find_node_by_id(r.shape_id)
    assert shape.data["convexshapes"] and shape.data["spheres"]


# ── the migration ───────────────────────────────────────────────────────────

def _old_doc():
    """A graph written before 1.6.28: the proxy chain with the url on the shape."""
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"convexshapes": [[0, 0, 0, 1, 1, 1, 2, 0, 0, 0, 2, 2]]})
    shape = g.find_node_by_id(r.shape_id)
    shape.url = "proxies/US1.glb"
    shape.data["url"] = "proxies/US1.glb"
    return json.loads(json.dumps(build_emjson(g))), r.shape_id


def test_an_old_graph_with_a_url_opens_with_the_resource():
    doc, shape_id = _old_doc()
    g, _ = parse_emjson(doc)
    shape = g.find_node_by_id(shape_id)
    assert shape.url == "" and "url" not in shape.data
    rid = proxy_resource_id(shape_id)
    assert g.find_node_by_id(rid).data["url"] == "proxies/US1.glb"
    assert (shape_id, "has_linked_resource", rid) in _triples(g)


def test_a_second_open_does_not_duplicate_it():
    doc, _ = _old_doc()
    once, _ = parse_emjson(doc)
    twice, _ = _reopen(once)
    assert len(_resources(twice)) == len(_resources(once)) == 1
    assert _triples(twice) == _triples(once)
    # and opening the ORIGINAL again lands on the same ids
    again, _ = parse_emjson(doc)
    assert {n.node_id for n in again.nodes} == {n.node_id for n in once.nodes}


def test_the_emtools_form_is_migrated():
    """graph_updaters.update_semantic_shapes: US ─has_semantic_shape→ '<US>_shape'
    with url proxies/<US>.glb, no property."""
    g = _studio()
    g.add_node(SemanticShapeNode("US1_shape", "US1_shape", type="proxy",
                                 url="proxies/US1.glb"))
    g.add_edge("US1_has_shape_US1_shape", "US1", "US1_shape", "has_semantic_shape")
    back, _ = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    t = _triples(back)
    assert ("US1", "has_semantic_shape", "US1_shape") not in t
    props = [x for (s, e, x) in t if s == "US1" and e == "has_property"]
    assert len(props) == 1 and (props[0], "has_semantic_shape", "US1_shape") in t
    rid = proxy_resource_id("US1_shape")
    assert ("US1_shape", "has_linked_resource", rid) in t
    assert back.find_node_by_id(rid).data["url_type"] == "proxy_model"
    assert back.find_node_by_id("US1_shape").url == ""


def test_the_heriverse_export_resource_is_reused_not_doubled():
    """operator.py _registra_bake: the shape already links a distribution
    resource with the same path (url_type left at 'External link')."""
    g = _studio()
    g.add_node(SemanticShapeNode("US1_shape", "US1_shape", type="proxy",
                                 url="proxies/US1.glb"))
    g.add_edge("x", "US1", "US1_shape", "has_semantic_shape")
    g.add_node(ResourceNode("US1_shape_link", name="US1.glb", url="proxies/US1.glb"))
    g.add_edge("y", "US1_shape", "US1_shape_link", "has_linked_resource")
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    res = _resources(back)
    assert [r.node_id for r in res] == ["US1_shape_link"], warnings
    assert res[0].data["url_type"] == "proxy_model"
    assert back.find_node_by_id("US1_shape").url == ""


def test_a_different_path_is_not_guessed_between():
    g = _studio()
    g.add_node(SemanticShapeNode("S", "S", type="proxy", url="proxies/new.glb"))
    g.add_node(ResourceNode("R", name="old.glb", url="proxies/old.glb",
                            url_type="proxy_model"))
    g.add_edge("y", "S", "R", "has_linked_resource")
    back, warnings = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    assert back.find_node_by_id("S").url == "proxies/new.glb"
    assert any("url left on the shape" in w for w in warnings)


def test_a_reading_glb_is_not_a_proxy():
    """A shape under an annotation region is a reading's, not a unit's proxy."""
    from s3dgraphy.geometry.migrate import migrate_shape_urls
    from s3dgraphy.nodes.annotation_region_node import AnnotationRegionNode
    g = Graph(graph_id="g")
    g.add_node(AnnotationRegionNode("A", "A", geometry_kind="point", vertex_count=1))
    g.add_node(SemanticShapeNode("S", "S", type="generic", url="readings/A.glb"))
    g.add_edge("h", "A", "S", "has_semantic_shape")
    assert migrate_shape_urls(g)["migrated"] == []
    assert not _resources(g)


# ── the consumers ───────────────────────────────────────────────────────────

def test_store_backed_lists_the_proxy_bound_to_its_unit():
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb"})
    res = g.find_node_by_id(r.resource_id)
    res.data["checksum"] = "sha256:" + "ab" * 32
    res.data["residency"] = "resident"
    rows = store_backed_geometry(g)
    assert len(rows) == 1
    row = rows[0]
    assert (row["node_id"], row["resource_id"], row["kind"]) == (
        r.shape_id, r.resource_id, "proxy")
    assert {b["id"] for b in row["bind"]} >= {r.property_id, "US1"}


def test_a_proxy_on_somebodys_disk_is_not_fetchable():
    g = _studio()
    create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb"})
    assert store_backed_geometry(g) == []


def _ttl(g):
    return api.project_ttl(g)


def test_the_rdf_carries_the_P67_and_round_trips_isomorphic():
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb",
                                         "convexshapes": [[0, 0, 0, 1, 0, 0, 0, 1, 0]]})
    ttl1 = _ttl(g)
    store = rdflib.ConjunctiveGraph()
    store.parse(data=ttl1, format="trig")
    p67 = [(s, o) for s, o in store.subject_objects(CRM.P67_refers_to)
           if str(s).endswith(r.shape_id) and str(o).endswith(r.resource_id)]
    assert p67, "the shape's has_linked_resource did not leave as P67"
    back = RDFImporter().parse(ttl1)[0]
    assert (r.shape_id, "has_linked_resource", r.resource_id) in _triples(back)
    assert back.find_node_by_id(r.resource_id).data["url_type"] == "proxy_model"
    ttl2 = _ttl(back)
    g1, g2 = rdflib.ConjunctiveGraph(), rdflib.ConjunctiveGraph()
    g1.parse(data=ttl1, format="trig")
    g2.parse(data=ttl2, format="trig")
    assert isomorphic(g1, g2), f"{len(g1)} vs {len(g2)} triples"


def test_heriverse_still_finds_the_path_on_the_shape():
    """Heriverse.js createSemanticNodeFromShape reads semantic_shapes[id].data.url:
    the Heriverse JSON projects the resource's path there."""
    from s3dgraphy.exporter.json_exporter import JSONExporter
    g = _studio()
    r = create_geometry_proxy(g, "US1", {"url": "proxies/US1.glb"})
    nodes = JSONExporter.__new__(JSONExporter)._process_nodes(g)
    assert nodes["semantic_shapes"][r.shape_id]["data"]["url"] == "proxies/US1.glb"
