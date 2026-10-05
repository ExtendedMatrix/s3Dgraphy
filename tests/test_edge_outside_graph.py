"""T-B3 · an edge with an end in another graph of the study is refused, in the
CRDT and in the reader, with the same sentence.

Before (5 Oct 2026): the CRDT took the edge (``crdt.apply_op_to_section``) and
the reader dropped it with a generic ``Both nodes … must exist`` — a room
accepted what its own file threw away. A link between graphs of one study
(I-4) does not exist yet; until it does, both places refuse.

An end that is in NO graph is another case, left as it was: the CRDT takes the
edge (its node may not have arrived yet, and the result must not depend on the
order — the parity fixture applies the ops reversed), the reader drops it.
"""
import copy
import json

from s3dgraphy.container import parse_container
from s3dgraphy.crdt import (apply_op_to_section, apply_ops_to_section,
                            edge_outside_graph, refusal_is_news)


def _unit(node_id, name):
    return {"id": node_id, "node_type": "US", "name": name, "description": "",
            "data": {}}


def _study():
    return {
        "header": {"format": "em.json", "version": "1.0"},
        "graphs": {
            "scavo": {"graph_id": "scavo", "name": "Scavo",
                      "nodes": [_unit("us1", "US1"), _unit("us2", "US2")],
                      "edges": []},
            "saggio": {"graph_id": "saggio", "name": "Saggio 30 m più avanti",
                       "nodes": [_unit("us9", "US9")], "edges": []},
        },
        "active_graph_id": "scavo",
    }


def _edge(source, target, ts="2026-10-05T10:00:00Z"):
    return {"op": "add_edge", "source": source, "target": target,
            "edge_type": "is_after", "ts": ts, "author": "dev"}


def test_the_crdt_refuses_an_edge_towards_another_graph():
    study = _study()
    section = study["graphs"]["scavo"]
    result = apply_op_to_section(section, _edge("us1", "us9"), study=study)
    assert result.applied is False
    assert result.reason == (
        "the node 'us9' is in the graph 'saggio', not in this one: an edge "
        "joins two nodes of the same graph, and a link between graphs does not "
        "exist yet")
    assert refusal_is_news(result.reason)          # the person is told
    assert section["edges"] == []                  # nothing written


def test_the_api_passes_the_study():
    from s3dgraphy import api
    study = _study()
    out = api.apply_op(study["graphs"]["scavo"], _edge("us9", "us1"), study=study)
    assert out["applied"] is False and "graph 'saggio'" in out["reason"]


def test_an_edge_inside_its_graph_is_taken():
    study = _study()
    section = study["graphs"]["scavo"]
    result = apply_op_to_section(section, _edge("us1", "us2"), study=study)
    assert result.applied is True
    assert len(section["edges"]) == 1


def test_a_removed_node_is_still_in_its_graph():
    study = _study()
    section = study["graphs"]["scavo"]
    apply_op_to_section(section, {"op": "remove_node", "id": "us2",
                                  "ts": "2026-10-05T10:00:00Z", "author": "dev"})
    result = apply_op_to_section(section, _edge("us1", "us2", "2026-10-05T10:01:00Z"),
                                 study=study)
    assert result.applied is True


def test_an_end_that_has_not_arrived_yet_does_not_decide_the_order():
    """The edge before its node, then the node: the same section as the other
    order. Refusing an end that is in no graph would break this."""
    study = _study()
    add = {"op": "add_node", "id": "us3", "node": _unit("us3", "US3"),
           "ts": "2026-10-05T10:00:00Z", "author": "dev", "lang": "it"}
    one, two = copy.deepcopy(study), copy.deepcopy(study)
    apply_ops_to_section(one["graphs"]["scavo"], [add, _edge("us1", "us3")])
    for op in [_edge("us1", "us3"), add]:
        apply_op_to_section(two["graphs"]["scavo"], op, study=two)
    assert one["graphs"]["scavo"]["edges"] == two["graphs"]["scavo"]["edges"]


def test_without_the_study_the_section_is_all_there_is():
    section = _study()["graphs"]["scavo"]
    assert apply_op_to_section(section, _edge("us1", "us9")).applied is True


def test_the_reader_refuses_it_with_the_same_sentence():
    study = _study()
    study["graphs"]["scavo"]["edges"].append(
        {"id": "e1", "source": "us1", "target": "us9", "edge_type": "is_after"})
    container, warnings = parse_container(json.loads(json.dumps(study)))
    sentence = edge_outside_graph(lambda i: i != "us9", "us1", "us9",
                                  lambda i: "saggio")
    assert any(sentence in w for w in warnings), warnings
    assert not container.graphs["scavo"].edges


def test_the_crdt_and_the_reader_say_the_same_thing():
    study = _study()
    crdt_reason = apply_op_to_section(study["graphs"]["scavo"],
                                      _edge("us9", "us1"), study=study).reason
    study = _study()
    study["graphs"]["scavo"]["edges"].append(
        {"id": "e1", "source": "us9", "target": "us1", "edge_type": "is_after"})
    _container, warnings = parse_container(study)
    assert any(w.endswith(crdt_reason) for w in warnings), warnings
