"""The proxies migrated from EMtools are found (MICRO le annotazioni ATON
sull'asset e la dev23, 2026-10-15, part 2).

The fixtures in ``fixtures/emtools_proxy/`` are MEASURED, not drawn: an em.json
written by the code of EMtools before 21dcf93 (``graph_updaters`` makes
``US1 ─has_semantic_shape→ 'US1_shape'(url proxies/US1.glb)``; the Heriverse
export's ``_registra_bake`` hangs off the shape a ``blend://`` master and the
``'US1_shape_link'`` distribution with the same path) — run through
``resource_levels.py`` at ``21dcf93^``:

* ``pre_21dcf93_external_link`` — as written: the distribution is
  ``External link`` (``promote_resource`` without a media type);
* ``pre_21dcf93_3d_model`` — the same, the distribution typed ``3d_model``
  (the case of EMtools' ``test_proxy_chain``: the migration of 1.6.0.dev22 left
  it as it was, and ``linked_proxy_resources`` did not see it);
* ``opened_by_dev22_3d_model`` — the second one opened and saved by the
  1.6.0.dev22 EMtools bundles (source 0573ea4): the shape's url already gone,
  the distribution still ``3d_model``.

What is defended: each opens with ONE ``proxy_model`` resource, the
distribution, which ``linked_proxy_resources`` finds; the ``blend://`` master
stays ``3d_model``; the ``3d_model`` of something that is not a unit's proxy
(a reading beyond the threshold, a shape owned by no property) stays
``3d_model``; a second opening changes nothing.
"""

import json
import pathlib

import pytest

from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.geometry import linked_proxy_resources, migrate_shape_urls
from s3dgraphy.graph import Graph
from s3dgraphy.importer.emjson_importer import parse_emjson
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.nodes.semantic_shape_node import SemanticShapeNode

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "emtools_proxy"
ALL = ["pre_21dcf93_external_link", "pre_21dcf93_3d_model", "opened_by_dev22_3d_model"]


def _open(name):
    return parse_emjson(json.loads((FIXTURES / f"{name}.em.json").read_text("utf-8")))


def _types(g):
    return {n.node_id: n.data.get("url_type") for n in g.nodes if n.node_type == "resource"}


def _snapshot(g):
    return (sorted((n.node_id, json.dumps(n.data, sort_keys=True, default=str)) for n in g.nodes),
            sorted((e.edge_source, e.edge_type, e.edge_target) for e in g.edges))


@pytest.mark.parametrize("name", ALL)
def test_the_migrated_proxy_has_one_proxy_model_resource(name):
    g, warnings = _open(name)
    assert _types(g) == {"US1_shape_link": "proxy_model", "US1_shape_res_blend": "3d_model"}, warnings
    assert [r.node_id for r in linked_proxy_resources(g, "US1_shape")] == ["US1_shape_link"]
    assert g.find_node_by_id("US1_shape_link").data["url"] == "proxies/US1.glb"
    assert not g.find_node_by_id("US1_shape").data.get("url")
    # the chain: US1 → Property(geometry) → shape
    t = {(e.edge_source, e.edge_type, e.edge_target) for e in g.edges}
    assert ("US1", "has_semantic_shape", "US1_shape") not in t
    [prop] = [x for (s, e, x) in t if s == "US1" and e == "has_property"]
    assert (prop, "has_semantic_shape", "US1_shape") in t


@pytest.mark.parametrize("name", ALL)
def test_a_second_opening_changes_nothing(name):
    once, _ = _open(name)
    twice, _ = parse_emjson(json.loads(json.dumps(build_emjson(once))))
    assert _snapshot(twice) == _snapshot(once)
    assert migrate_shape_urls(twice)["retyped"] == []


def test_a_3d_model_that_is_no_units_proxy_stays_3d_model():
    """A shape no geometry property carries (a leftover, a generic shape)
    reusing a 3d_model with its own path keeps it as written."""
    g = Graph(graph_id="g")
    g.add_node(SemanticShapeNode("S", "S", type="generic", url="scans/wall.glb"))
    g.add_node(ResourceNode("R", name="wall.glb", url="scans/wall.glb", url_type="3d_model"))
    g.add_edge("y", "S", "R", "has_linked_resource")
    report = migrate_shape_urls(g)
    assert report["retyped"] == [] and g.find_node_by_id("R").data["url_type"] == "3d_model"


def test_a_reading_beyond_the_threshold_stays_3d_model():
    from s3dgraphy import api
    from s3dgraphy.nodes import ExtractorNode, RepresentationModelNode
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", "Model"))
    g.add_node(ExtractorNode("X1", name="D.1.1"))
    r = api.place_reading(g, "X1", "RM1", {"geometry_kind": "polyline",
                                           "vertices": [[i, 0, 0] for i in range(501)]})
    back, _ = parse_emjson(json.loads(json.dumps(build_emjson(g))))
    assert back.find_node_by_id(r.resource_id).data["url_type"] == "3d_model"


def test_two_3d_model_distributions_are_not_guessed_between():
    g, _ = _open("opened_by_dev22_3d_model")
    g.find_node_by_id("US1_shape_link").data["url_type"] = "3d_model"
    g.add_node(ResourceNode("other", name="other.glb", url="proxies/other.glb",
                            url_type="3d_model", tier="distribution"))
    g.add_edge("z", "US1_shape", "other", "has_linked_resource")
    report = migrate_shape_urls(g)
    assert report["retyped"] == [] and report["warnings"]
    assert linked_proxy_resources(g, "US1_shape") == []
