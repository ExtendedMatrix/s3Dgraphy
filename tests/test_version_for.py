"""The version for a use (E.D., 5 Oct 2026: «Heriverse legge l'em.json e
sceglie la versione»). Nothing is exported for a viewer: the viewer reads the
study and picks, among the resources of a representation model, the one to load.

The rule is ``choose_version``; the cases of ``JSON_config/version_for_cases.json``
are the contract every copy passes — here in Python, and in JS through
Heriverse's ``tests/check-version-for.mjs`` when that checkout is beside this one.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources import versions as V

CASES_PATH = (Path(V.__file__).resolve().parent.parent
              / "JSON_config" / "version_for_cases.json")
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_the_cases_of_the_rule(case):
    got = V.choose_version(case["entries"], case["use"], case.get("prefer_level"))
    want = case["expect"]
    if want is None:
        assert got is None
        return
    assert (got["entry"] or {}).get("id") == want["id"]
    assert got["reason"] == want["reason"]
    assert got["use"] == want["use"]
    assert bool(got["note"]) == want["note"], got["note"]


def _study():
    """An RM with a master and two versions (web lod1, web+preview lod2 of
    lod1, analysis lod0), and an RM with only its master."""
    g = Graph("version-for")
    api.add_resource(g, name="podio", kind="3d_model", tier="master",
                     files=[{"path": "podio.glb", "checksum": "sha256:" + "0" * 64}],
                     resource_id="podio")
    v0 = api.add_version(g, "podio", use="analysis",
                         files=[{"path": "LOD0/podio.glb", "checksum": "sha256:" + "1" * 64}])
    v1 = api.add_version(g, v0["version_id"], use="web",
                         files=[{"path": "LOD1/podio.glb", "checksum": "sha256:" + "2" * 64}])
    v2 = api.add_version(g, v1["version_id"], use=["web", "preview"],
                         files=[{"path": "LOD2/podio.glb", "checksum": "sha256:" + "3" * 64}])
    api.add_resource(g, name="muro", kind="3d_model",
                     files=[{"path": "muro.glb", "checksum": "sha256:" + "4" * 64}],
                     resource_id="muro")
    for rm_id, res in (("rm_podio", "podio"), ("rm_muro", "muro")):
        g.add_node(RepresentationModelNode(node_id=rm_id, name=rm_id))
        g.add_edge(f"{rm_id}_res", rm_id, res, "has_linked_resource")
    return g, v0, v1, v2


def test_from_the_representation_model_the_lightest_web_version():
    g, v0, v1, v2 = _study()
    got = api.version_for(g, "rm_podio", "web")
    assert got["entry"]["id"] == v2["version_id"]
    assert got["entry"]["lod_level"] == "lod2"
    assert got["entry"]["checksum"] == "sha256:" + "3" * 64
    assert (got["reason"], got["use"], got["asset_id"]) == ("use", "web", "podio")


def test_the_level_asked_for():
    g, v0, v1, v2 = _study()
    got = api.version_for(g, "rm_podio", "web", prefer_level="lod1")
    assert (got["entry"]["id"], got["reason"]) == (v1["version_id"], "level")


def test_from_a_version_the_same_answer_as_from_its_asset():
    g, v0, v1, v2 = _study()
    assert api.version_for(g, v0["version_id"], "web")["entry"]["id"] == v2["version_id"]


def test_web_then_realtime_and_then_the_master_said():
    g, *_ = _study()
    got = api.version_for(g, "rm_muro", ["web", "realtime"])
    assert (got["entry"]["id"], got["reason"]) == ("muro", "master")
    assert "master" in got["note"] and "web, realtime" in got["note"]


def test_a_use_nobody_declares_falls_on_the_master():
    g, *_ = _study()
    got = api.version_for(g, "rm_podio", "mobile_ar")
    assert (got["entry"]["id"], got["reason"]) == ("podio", "master")


def test_an_rm_without_resources_has_nothing_to_load():
    g = Graph("empty")
    g.add_node(RepresentationModelNode(node_id="rm", name="rm"))
    assert api.version_for(g, "rm", "web") is None


HERI = Path(os.environ.get("HERI") or Path(__file__).resolve().parents[2] / "Heriverse")


@pytest.mark.skipif(not (HERI / "tests" / "check-version-for.mjs").exists()
                    or shutil.which("node") is None,
                    reason="Heriverse checkout or node not beside this one")
def test_the_same_cases_pass_in_js():
    out = subprocess.run(["node", str(HERI / "tests" / "check-version-for.mjs")],
                         env={**os.environ, "HERI": str(HERI),
                              "VERSION_FOR_CASES": str(CASES_PATH)},
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_viewer_asks_first_the_version_made_for_it():
    """H4 · a version made for Heriverse (the package on disk) comes before any
    web version, even a lighter one; the order is ``VIEWER_USES``."""
    g, v0, v1, v2 = _study()
    vh = api.add_version(g, "podio", use=["heriverse", "aton"], level="heriverse",
                         files=[{"path": "versions/podio.glb",
                                 "checksum": "sha256:" + "5" * 64}])
    assert V.VIEWER_USES == ("heriverse", "aton", "web", "realtime")
    got = api.version_for(g, "rm_podio", list(V.VIEWER_USES))
    assert (got["entry"]["id"], got["use"]) == (vh["version_id"], "heriverse")
    assert api.version_for(g, "rm_muro", list(V.VIEWER_USES))["reason"] == "master"


def test_heriverse_and_aton_are_uses():
    assert V.check_use(["heriverse", "aton"]) == ["heriverse", "aton"]
