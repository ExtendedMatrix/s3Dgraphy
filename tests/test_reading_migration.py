"""Migration in reading: EMStudio's `data.geometry` (from 2026-10-05) becomes a
place node the extractor extracted_from (MICRO la geometria della lettura, 3).

The fixture carries the two cases EMStudio writes: a passage of a text and a
point on a 3D model.
"""

import copy
import json

from s3dgraphy import api
from s3dgraphy.exporter.emjson_exporter import build_emjson
from s3dgraphy.geometry.reading_glb import read_glb
from s3dgraphy.importer.emjson_importer import parse_emjson

POINT = [12.5, 1.75, -4.25]


def _doc():
    return {
        "header": {"format": "em.json", "version": "1.0"},
        "graph": {
            "graph_id": "g",
            "name": "legacy readings",
            "nodes": [
                {"id": "D1", "node_type": "document", "name": "D.1"},
                {"id": "RM1", "node_type": "representation_model", "name": "wall.glb"},
                {"id": "X1", "node_type": "extractor", "name": "D.1.1",
                 "data": {"geometry": {"kind": "passage", "start": 4, "end": 19,
                                       "text": "opera reticolata"}}},
                {"id": "X2", "node_type": "extractor", "name": "RM.1",
                 "data": {"geometry": {"kind": "point3d", "p": POINT,
                                       "on": "wall.glb"}}},
            ],
            "edges": [
                {"id": "e1", "source": "X1", "target": "D1", "edge_type": "extracted_from"},
            ],
        },
    }


def _reads(graph, xid):
    return [graph.find_node_by_id(e.edge_target) for e in graph.edges
            if e.edge_source == xid and e.edge_type == "extracted_from"]


def _region_of(graph, xid):
    regs = [n for n in _reads(graph, xid) if n.node_type == "annotation_region"]
    assert len(regs) == 1, regs
    return regs[0]


def test_opening_the_file_migrates_both_and_writes_the_point_glb(tmp_path):
    path = tmp_path / "study.em.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    graph, warnings = api.load_emjson_file(str(path))

    passage = _region_of(graph, "X1")
    assert passage.geometry_kind == "passage"
    assert (passage.start, passage.end, passage.text) == (4, 19, "opera reticolata")
    assert any(e.edge_source == passage.node_id and e.edge_type == "is_on_resource"
               and e.edge_target == "D1" for e in graph.edges)

    point = _region_of(graph, "X2")
    assert point.geometry_kind == "point" and point.data["vertex_count"] == 1
    # `on` named the model by its name: resolved to the node
    assert any(e.edge_source == point.node_id and e.edge_type == "is_on_resource"
               and e.edge_target == "RM1" for e in graph.edges)
    glb = tmp_path / "readings" / f"{point.node_id}.glb"
    assert read_glb(str(glb)) == {"geometry_kind": "point", "vertices": [POINT]}

    # the old field is read, not written again
    for xid in ("X1", "X2"):
        assert "geometry" not in graph.find_node_by_id(xid).data
    out = json.dumps(build_emjson(graph))
    assert '"kind": "passage"' not in out and '"point3d"' not in out
    assert not [w for w in warnings if "reading migration" in w], warnings


def test_opening_twice_is_a_no_op(tmp_path):
    path = tmp_path / "study.em.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    first, _ = api.load_emjson_file(str(path))
    path.write_text(json.dumps(build_emjson(first)), encoding="utf-8")
    second, _ = api.load_emjson_file(str(path))
    ids = lambda g: sorted(n.node_id for n in g.nodes)
    assert ids(first) == ids(second)
    assert len(first.edges) == len(second.edges)


def test_without_a_folder_the_point_keeps_its_only_copy():
    graph, warnings = parse_emjson(copy.deepcopy(_doc()))
    # the passage needs no file: migrated
    assert "geometry" not in graph.find_node_by_id("X1").data
    # the point: region made, coordinates kept where they are, and said so
    region = _region_of(graph, "X2")
    assert graph.find_node_by_id("X2").data["geometry"]["p"] == POINT
    assert any("keeps its data.geometry" in w and region.node_id in w for w in warnings)


def test_the_pending_point_completes_on_the_next_open_from_a_file(tmp_path):
    graph, _ = parse_emjson(copy.deepcopy(_doc()))
    path = tmp_path / "study.em.json"
    path.write_text(json.dumps(build_emjson(graph)), encoding="utf-8")
    again, warnings = api.load_emjson_file(str(path))
    region = _region_of(again, "X2")
    assert "geometry" not in again.find_node_by_id("X2").data
    assert (tmp_path / "readings" / f"{region.node_id}.glb").is_file()
    assert region.node_id == _region_of(graph, "X2").node_id


def test_a_region_already_read_shadows_the_legacy_field():
    doc = _doc()
    doc["graph"]["nodes"].append({"id": "R0", "node_type": "annotation_region", "name": "r",
                                  "data": {"shape_kind": "rect", "rect": [0, 0, .5, .5]}})
    doc["graph"]["edges"].append({"id": "e2", "source": "X1", "target": "R0",
                                  "edge_type": "extracted_from"})
    graph, _ = parse_emjson(doc)
    assert graph.find_node_by_id("X1").data["geometry"]["kind"] == "passage"
    assert [n.node_id for n in _reads(graph, "X1") if n.node_type == "annotation_region"] == ["R0"]


def test_an_unknown_kind_is_left_alone_and_said():
    doc = _doc()
    doc["graph"]["nodes"][2]["data"]["geometry"] = {"kind": "volume"}
    graph, warnings = parse_emjson(doc)
    assert graph.find_node_by_id("X1").data["geometry"] == {"kind": "volume"}
    assert any("'volume'" in w for w in warnings)


def test_a_container_file_migrates_its_members_with_the_file_folder(tmp_path):
    single = _doc()
    container = {"header": single["header"], "active_graph_id": "g",
                 "graphs": {"g": single["graph"]}}
    path = tmp_path / "project.em.json"
    path.write_text(json.dumps(container), encoding="utf-8")
    loaded, _ = api.load_container_file(str(path))
    graph = loaded.graphs["g"]
    region = _region_of(graph, "X2")
    assert (tmp_path / "readings" / f"{region.node_id}.glb").is_file()
    assert "geometry" not in graph.find_node_by_id("X2").data
