"""MICRO le alternative e la trasformazione, Parte 2 — the sets of alternatives.

E.D., 17 Oct 2026: two resources are alternatives if and only if they have the
same hat. ``alternative_sets`` gives, for every RM and every RM container, the
set of its alternatives with the computed reason (lod, fidelity, packaging),
nested (a container's members under it) and diagnosed. The cases of
``JSON_config/alternative_cases.json`` are the contract EMStudio and Heriverse
pass too.
"""
import json
import os
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.resources import versions as V
from s3dgraphy.resources.alternatives import (alternative_sets, choose_alternative,
                                              declare_alternative, find_set, iter_sets,
                                              make_subcontainer)

CONFIG = Path(V.__file__).resolve().parent.parent / "JSON_config"
CASES = json.loads((CONFIG / "alternative_cases.json").read_text("utf-8"))["cases"]

#: Templu Mare v2 for 3DR (6 Oct 2026), read only: TEMPLU_MARE_EM points at its
#: EM folder (default: E.D.'s OneDrive copy).
TEMPLU = Path(os.environ.get("TEMPLU_MARE_EM", os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-CNR/0_RACCOLTA_CNR/StratiGraph-grp - Documenti/"
    "WP 06 - Web Environment Development/T6.5/TempluMare_v2_for_3DR_2026-10-06/EM")))


def _graph(section):
    doc = {"header": {"format": "em.json", "version": "1.0", "schema_version": 2},
           "graph": {"graph_id": "case", **section}}
    g, _ = api.load_emjson(doc)
    return g


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_the_cases_of_the_rule(case):
    g = _graph(case["graph"])
    res = alternative_sets(g)
    got = [{"hat": s["hat"], "hat_kind": s["hat_kind"], "parent": s["parent"],
            "alternatives": [[x["id"], x["reason"]] for x in s["alternatives"]],
            "reasons": s["reasons"], "covers": s["covers"], "coverage": s["coverage"]}
           for s in iter_sets(res)]
    assert got == case["expect"]["sets"]
    assert sorted(w["code"] for w in res["warnings"]) == case["expect"]["warnings"]
    assert res["counts"] == case["expect"]["counts"]
    for c in case["choices"]:
        ch = choose_alternative(find_set(res, c["hat"]), c["use"], force=c.get("force"))
        want = c["expect"]
        assert ch["level"] == want["level"]
        assert (ch["entry"] or {}).get("id") == want["id"]
        assert ch["use"] == want["use"]
        if "members" in want:
            assert {h: (m["entry"] or {}).get("id") for h, m in ch["members"].items()} == want["members"]


def test_choose_version_takes_a_set_at_both_levels():
    case = CASES[0]
    res = alternative_sets(_graph(case["graph"]))
    container = V.choose_version(find_set(res, "survey_rmgroup"), ["web"])
    assert container["level"] == "container" and container["entry"]["id"] == "tiles.lod0"
    rm = V.choose_version(find_set(res, "EST_0_model"), ["aton"])
    assert rm["level"] == "rm" and rm["entry"]["id"] == "EST_0.lod1"
    # and a list of entries still works as before
    assert V.choose_version(find_set(res, "EST_0_model")["alternatives"], "aton")["entry"]["id"] == "EST_0.lod1"


def test_the_warnings_carry_their_cure():
    for case in CASES:
        for w in alternative_sets(_graph(case["graph"]))["warnings"]:
            assert w["message"] and w["cure"] and w["code"] in ("two_hats", "partial_coverage", "epochs")


def test_partial_coverage_is_measured_on_the_boxes_a_consumer_passes():
    g = _graph(CASES[0]["graph"])
    boxes = {f"EST_{i}_model": [[i * 10, 0, 0], [i * 10 + 10, 10, 10]] for i in range(4)}
    whole = alternative_sets(g, bounds={**boxes, "tiles.lod0": [[0, 0, 0], [40, 10, 10]]})
    assert find_set(whole, "survey_rmgroup")["coverage"] == "whole"
    part = alternative_sets(g, bounds={**boxes, "tiles.lod0": [[0, 0, 0], [30, 10, 10]]})
    assert find_set(part, "survey_rmgroup")["coverage"] == "partial"
    (w,) = part["warnings"]
    assert w["code"] == "partial_coverage" and w["ids"] == ["EST_0_model", "EST_1_model", "EST_2_model"]
    # the cure: the covered part as a sub-container, the tileset its alternative
    sub = make_subcontainer(g, "survey_rmgroup", w["ids"], "Survey · west")["group_id"]
    declare_alternative(g, "tiles.master", sub)
    cured = alternative_sets(g, bounds={**boxes, "tiles.lod0": [[0, 0, 0], [30, 10, 10]]})
    assert cured["warnings"] == []
    assert find_set(cured, sub)["coverage"] == "whole"
    assert find_set(cured, sub)["parent"] == "survey_rmgroup"
    assert find_set(cured, "survey_rmgroup")["covers"] == ["EST_3_model", "EST_0_model",
                                                           "EST_1_model", "EST_2_model"]


def test_a_container_across_epochs_with_an_alternative_is_warned():
    g = _graph(CASES[0]["graph"])
    from s3dgraphy.nodes.epoch_node import EpochNode
    g.add_node(EpochNode("ep2", name="II AD", start_time=100, end_time=200))
    for e in list(g.edges):
        if e.edge_type == "has_representation_model" and e.edge_target == "EST_3_model":
            g.remove_edge(e.edge_id)
    g.add_edge("ep2_rm_EST_3", "ep2", "EST_3_model", "has_representation_model")
    codes = [w["code"] for w in alternative_sets(g)["warnings"]]
    assert codes == ["epochs"]


@pytest.mark.parametrize("name", ["TempluMare_v2.em.json", "TempluMare_v3.2.em.json"])
def test_templu_mare(name):
    path = TEMPLU / name
    if not path.exists():
        pytest.skip(f"{path} absent")
    g, _ = api.load_emjson_file(str(path))
    res = alternative_sets(g)
    c = res["counts"]
    # measured on 17 Oct 2026: 99 RMs, one asset each, no container; every RM
    # has its master and at least one version; XX_tileset has one level only
    assert c["sets"] == 99 and c["containers"] == 0 and c["with_alternatives"] == 99
    assert c["by_reason"] == {"lod": 98, "fidelity": 99, "packaging": 0}
    assert c["entries"] == 329
    assert res["warnings"] == []
    tiles = find_set(res, "XX_tileset_model")
    assert [x["tileset"] for x in tiles["alternatives"]] == [True, True]
    assert [x["lod_level"] for x in tiles["alternatives"]] == [None, "lod0"]
    assert tiles["alternatives"][1]["measures"] == {"geometric_error_m": 6.144}
