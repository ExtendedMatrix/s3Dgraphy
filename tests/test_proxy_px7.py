"""A point taken on a Gaussian splat says how (MICRO-PX7, 27 Nov 2026).

What is defended:

* ``proxy_from_points``: a point's ``attributes`` become attributes of its
  extractor — EMStudio's ``pick_rule`` / ``pick_opacity`` for a point read on
  a splat (the alpha isosurface at a threshold), no new node type — and never
  overwrite what the library writes itself (``point_type``, ``purpose``,
  ``x``/``y``/``z``, ``read_from``);
* a point without ``attributes`` is written as before;
* ``door.kind_of``: the splat files (``.spz``, ``.sog``, ``.rad``, ``.lcc2``,
  a SOG ``lod-meta.json``) are models (EMStudio's door.ts, the same answer).
"""

import itertools

from s3dgraphy.door import kind_of
from s3dgraphy.geometry.proxy_points import proxy_from_points
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _studio():
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", name="USM01"))
    g.add_node(DocumentNode("D1", name="D.01"))
    g.add_node(RepresentationModelNode("RM1", name="splat_2026"))
    return g


def _ids():
    n = itertools.count(1)
    return lambda: f"id{next(n)}"


PICK = {"pick_rule": "splat_alpha_isosurface", "pick_opacity": 0.5}


def _pt(**kw):
    p = {"document_id": "D1", "x": 1.0, "y": 2.0, "z": 3.0, "point_type": "plan", "coords": [1.0, 3.0, -2.0], "on_id": "RM1"}
    p.update(kw)
    return p


def test_a_point_on_a_splat_says_how_it_was_taken():
    g = _studio()
    out = proxy_from_points(g, "US1", [_pt(attributes=PICK), _pt()], new_id=_ids())
    a, b = (g.find_node_by_id(x) for x in out.extractor_ids)
    assert a.attributes["pick_rule"] == "splat_alpha_isosurface"
    assert a.attributes["pick_opacity"] == 0.5
    assert a.attributes["point_type"] == "plan"
    # the other point, on a mesh: nothing said, as before
    assert "pick_rule" not in b.attributes and "pick_opacity" not in b.attributes


def test_the_attributes_never_overwrite_the_librarys_own():
    g = _studio()
    bad = dict(PICK, point_type="x", purpose="y", x=9.0, y=9.0, z=9.0, read_from="nope", empty=None)
    out = proxy_from_points(g, "US1", [_pt(attributes=bad)], purpose="wall_from_plan", new_id=_ids())
    a = g.find_node_by_id(out.extractor_ids[0])
    assert a.attributes["point_type"] == "plan"
    assert a.attributes["purpose"] == "wall_from_plan"
    assert (a.attributes["x"], a.attributes["y"], a.attributes["z"]) == (1.0, 2.0, 3.0)
    assert "read_from" not in a.attributes
    assert "empty" not in a.attributes
    assert a.attributes["pick_rule"] == "splat_alpha_isosurface"


def test_splat_files_are_models_at_the_door():
    for n in ("a.spz", "b.SOG", "c.rad", "d.lcc2", "scene/lod-meta.json", "e.ply"):
        assert kind_of(n) == "model", n
    assert kind_of("meta.json") == "other"
    assert kind_of("tileset.json") == "tileset"
