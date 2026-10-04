"""V1 · one vocabulary of operations on every wire (Sidecar and room).

Measured on 4 Oct 2026: EMtools sent the room the Sidecar's `update_node` and
the library refused it («unknown operation 'update_node'»): a description
written in Blender never arrived. These tests hold the cure in place: one
translator (`crdt.ops_for_local_change`) and one validator (`crdt.validate_op`),
on cases that EMStudio's twin (`hub.ts` `opsForLocalChange`) answers too.
"""
import copy
import json
from pathlib import Path

import pytest

from s3dgraphy import crdt

CASES = json.loads((Path(__file__).parent / "data" / "op_vocabulary_cases.json")
                   .read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_each_case_translates_as_written(case):
    local = copy.deepcopy(case["local"])
    if "error" in case:
        with pytest.raises(ValueError) as e:
            crdt.ops_for_local_change(local, study_language=case.get("study_language"))
        assert case["error"] in str(e.value)
    else:
        ops = crdt.ops_for_local_change(local, study_language=case.get("study_language"))
        assert ops == case["ops"]
        assert all(crdt.validate_op(op) is None for op in ops)
    assert local == case["local"], "the translator must not touch the store's change"


def test_the_measured_defect_update_node_is_refused_by_name():
    section = {"nodes": [{"id": "US1", "node_type": "US", "description": "", "data": {}}], "edges": []}
    raw = {"op": "update_node", "node_id": "US1", "patch": {"description": "x"}}
    r = crdt.apply_op_to_section(section, raw)
    assert not r.applied and r.reason == "unknown operation 'update_node'"
    assert "ops_for_local_change" in crdt.validate_op(raw)


def test_a_description_written_in_blender_lands_in_the_room():
    """The same change, through the translator, is applied by the library the
    server runs — and the edge whose endpoints the Sidecar nested lands with
    them."""
    section = {"nodes": [{"id": "US1", "node_type": "US", "description": "", "data": {}}], "edges": []}
    changes = [
        {"op": "update_node", "node_id": "US1", "patch": {"description": "muro"},
         "ts": "2026-10-04T09:00:00Z"},
        {"op": "add_node", "node": {"id": "US2", "node_type": "US", "name": "US 2"},
         "ts": "2026-10-04T09:00:01Z"},
        {"op": "add_edge", "edge": {"id": "US2_is_after_US1", "source": "US2",
                                     "target": "US1", "edge_type": "is_after"}},
    ]
    for ch in changes:
        for op in crdt.ops_for_local_change(ch, study_language="it"):
            assert crdt.apply_op_to_section(section, op).applied, op
    us1 = next(n for n in section["nodes"] if n["id"] == "US1")
    assert us1["description"] == "muro"
    assert section["edges"][0]["source"] == "US2" and section["edges"][0]["target"] == "US1"
    us2 = next(n for n in section["nodes"] if n["id"] == "US2")
    assert us2["data"]["lang"] == "it"


def test_the_reverse_door_keeps_the_clock_and_round_trips():
    for case in CASES:
        if "ops" not in case:
            continue
        for op in case["ops"]:
            op = dict(op, author="orcid:0000-0002-1825-0097")
            local = crdt.local_change_for_op(op)
            assert local["author"] == op["author"] and local.get("ts") == op.get("ts")
            back = crdt.ops_for_local_change(local)
            assert len(back) == 1
            want = {k: v for k, v in op.items() if k != "author"}
            got = {k: v for k, v in back[0].items() if k != "author"}
            if want["op"] == "add_node":
                assert got["node"] == want["node"] and got["id"] == want["id"]
            else:
                assert got == want


def test_validator_sentences():
    assert crdt.validate_op({"op": "update_field", "node_id": "a", "field": "data.x"}) \
        .startswith("update_field of 'data.x' without a value")
    assert crdt.validate_op({"op": "remove_edge"}).startswith("remove_edge without")
    assert crdt.validate_op({"op": "remove_edge", "source": "a", "target": "b",
                             "edge_type": "is_after"}) is None
    assert crdt.validate_op("x") == "an operation is an object"


def test_which_refusals_are_news():
    assert not crdt.refusal_is_news("stale")
    assert not crdt.refusal_is_news("idempotent")
    assert crdt.refusal_is_news("unknown operation 'update_node'")
    assert crdt.refusal_is_news("node 'US7' is not here")
