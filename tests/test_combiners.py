"""The declared combiners (MICRO-PL08, row W4 of the extensions plan).

What is defended (node datamodel 1.6.51, SPEC-pacchetto §6, D-9):

* the operations of the closed set — distance, angle, ratio, mean,
  area_of_polygon, elevation_difference and D-9's angle_between_planes and
  symmetry_index — compute what they say, refuse a degenerate geometry and
  anything outside the set;
* computing a package's combiner writes ONE PropertyNode with the whole chain
  (unit → property → combiner → extractors → region → model), in the type's
  unit, idempotently; inputs not there are named, never guessed;
* the ratio waits for the distances it reads (the order of the package);
* when a point moves the values that read it are computed again, and so are
  the values that read THOSE; a value whose input is gone says it;
* what the combiner read is in the node: any tool recomputes it without the
  package, after em.json, on a georeferenced graph alike.
"""

import json
import math
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy import profiles as P
from s3dgraphy.annotation import combiners as C
from s3dgraphy.annotation import extractors as X
from s3dgraphy.annotation.reading import place_reading
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE = DATA / "esempio-statuaria"
# a small head (metres, glTF y up): nasion at the origin
FACE = {"glabella": [0.0, 0.012, 0.003], "nasion": [0.0, 0.0, 0.0],
        "exocanthion_r": [-0.042, -0.008, -0.012], "exocanthion_l": [0.042, -0.008, -0.012],
        "gnathion": [0.0, -0.1, 0.002]}


@pytest.fixture(scope="module")
def overlay():
    return P.ProfileOverlay([P.load(SEPARATE)])


def _graph():
    g = Graph(graph_id="g")
    g.add_node(RepresentationModelNode("RM1", name="RM head"))
    g.add_node(StratigraphicUnit("US1", "US1"))
    return g


def _posed(overlay, points=FACE, g=None):
    g = g or _graph()
    pose = X.start_landmark_pose(g, overlay, "stat:volto", "RM1", subject="US1")
    for k, v in points.items():
        X.place_landmark(g, overlay, "stat:volto", k, "RM1", v, pose_id=pose, subject="US1")
    return g, pose


def _edges(g, src=None, kind=None, tgt=None):
    return [e for e in g.edges if (src is None or e.edge_source == src)
            and (kind is None or e.edge_type == kind) and (tgt is None or e.edge_target == tgt)]


def _pkg(tmp_path, combiners, extra_points=None):
    """A copy of the example package with more combiner types."""
    import shutil
    root = tmp_path / "pkg"
    shutil.copytree(SEPARATE, root)
    prof = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    prof["combiner_types"] = prof["combiner_types"] + combiners
    known = {q["id"] for q in prof["qualia"]}
    for c in combiners:
        if c["produces"] not in known:
            prof["qualia"].append({"id": c["produces"], "label": {"it": c["produces"], "en": c["produces"]},
                                   "data_type": "float"})
            known.add(c["produces"])
    (root / "profile.json").write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
    return P.ProfileOverlay([P.load(root)])


# ── the datamodel ───────────────────────────────────────────────────────────

def test_the_datamodel_describes_a_declared_computation():
    dm = json.loads((Path(api.__file__).parent / "JSON_config" /
                     "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    assert dm["s3Dgraphy_data_model_version"] == "1.6.57"  # 1.6.57 MICRO pyArchInit seguito (source_code for every unit); 1.6.56 dal 23 nov 2026 (MICRO-LG12: PropertyNode data.placeholder, ExtractorNode data.source_strength / source_model); 1.6.55 dal 23 nov 2026 (MICRO-LG11: StratigraphicNode data.unnumbered, le unità senza numero); 1.6.54 dal 22 nov 2026 (MICRO-LG6: PropertyNode valid_from_doubtful, l'obliterazione); 1.6.53 dal 22 nov 2026 (MICRO-LG4: le finestre della visibilità, PropertyNode valid_*_epoch e forbice); 1.6.52 dal 21 nov 2026 (MICRO-LG2: l'unità funzionale nel tempo); 1.6.51 i combinatori dichiarati
    sub = dm["paradata_nodes"]["ParadataNode"]["subtypes"]
    comb = sub["CombinerNode"]["properties"]
    assert comb["combiner"]["em_json"] == "data.combiner"
    assert comb["em_kind"]["em_json"] == "data.em_kind"
    assert comb["landmark_pose"]["em_json"] == "data.landmark_pose"
    for op in P.OPERATIONS:
        assert op in comb["combiner"]["shape"]["operation"]
    assert sub["PropertyNode"]["properties"]["measure"]["em_json"] == "data.measure"


def test_every_operation_of_the_closed_set_has_its_quantity():
    assert set(C.QUANTITY) == set(P.OPERATIONS)


# ── the operations ──────────────────────────────────────────────────────────

def test_distance_angle_and_area():
    v, u, q = C.execute("distance", [[0, 0, 0], [3, 4, 0]])
    assert (v, u, q) == (5.0, "m", "length")
    assert C.execute("distance", [[0, 0, 0], [0.03, 0.04, 0]], "cm")[:2] == (5.0, "cm")
    assert C.execute("angle", [[1, 0, 0], [0, 0, 0], [0, 0, 1]])[:2] == (pytest.approx(90.0), "deg")
    assert C.execute("angle", [[1, 0, 0], [0, 0, 0], [0, 0, 1]], "rad")[0] == pytest.approx(math.pi / 2, abs=1e-6)
    # a 2 × 3 rectangle on the ground, and in cm2
    rect = [[0, 0, 0], [2, 0, 0], [2, 0, -3], [0, 0, -3]]
    assert C.execute("area_of_polygon", rect) == (6.0, "m2", "area")
    assert C.execute("area_of_polygon", rect, "cm2")[:2] == (60000.0, "cm2")


def test_the_elevation_difference_is_the_first_minus_the_second():
    assert C.execute("elevation_difference", [[0, 2.5, 0], [9, 1.0, 9]])[0] == pytest.approx(1.5)
    assert C.execute("elevation_difference", [[0, 1.0, 0], [0, 2.5, 0]])[0] == pytest.approx(-1.5)


def test_ratio_makes_the_units_equal():
    assert C.execute("ratio", [(0.12, "m"), (0.08, "m")])[:2] == (pytest.approx(1.5), "1")
    assert C.execute("ratio", [(12.0, "cm"), (0.08, "m")])[0] == pytest.approx(1.5)
    assert C.execute("ratio", [(12.0, "cm"), (0.08, "m")], "%")[:2] == (pytest.approx(150.0), "%")
    with pytest.raises(C.CombinerError, match="0"):
        C.execute("ratio", [(1.0, "m"), (0.0, "m")])
    with pytest.raises(C.CombinerError, match="same quantity"):
        C.execute("ratio", [(1.0, "m"), (1.0, "m2")])


def test_mean_of_qualia_and_of_points():
    assert C.execute("mean", [(1.0, "m"), (2.0, "m"), (3.0, "m")])[:2] == (2.0, "m")
    assert C.execute("mean", [(100.0, "cm"), (3.0, "m")])[:2] == (2.0, "m")
    assert C.execute("mean", [(1.2, None), (1.4, None)])[0] == pytest.approx(1.3)
    centre, unit, q = C.execute("mean", [[0, 0, 0], [2, 0, 0], [1, 3, 0]])
    assert centre == pytest.approx([1.0, 1.0, 0.0]) and q == "position"
    with pytest.raises(C.CombinerError):
        C.execute("mean", [[0, 0, 0], (1.0, "m")])


def test_the_angle_between_two_planes_has_no_side():
    ground = [[0, 0, 0], [1, 0, 0], [0, 0, 1]]
    wall = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]
    tilted = [[0, 0, 0], [1, 0, 0], [0, 1, 1]]
    assert C.execute("angle_between_planes", ground + wall)[0] == pytest.approx(90.0)
    assert C.execute("angle_between_planes", ground + tilted)[0] == pytest.approx(45.0)
    # the same plane written the other way round: 0, not 180
    assert C.execute("angle_between_planes", ground + list(reversed(ground)))[0] == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(C.CombinerError, match="one line"):
        C.execute("angle_between_planes", ground + [[0, 0, 0], [1, 0, 0], [2, 0, 0]])


def _roles():
    return [{"point": "a_r", "side": "right", "mirror": "a_l"}, {"point": "a_l", "side": "left", "mirror": "a_r"},
            {"point": "b_r", "side": "right", "mirror": "b_l"}, {"point": "b_l", "side": "left", "mirror": "b_r"},
            {"point": "mid"}]


def test_the_symmetry_index_is_zero_for_a_symmetric_set_and_does_not_scale():
    sym = [[-1, 0, 0], [1, 0, 0], [-0.5, -1, 0.2], [0.5, -1, 0.2], [0, 0.5, 0.3]]
    assert C.op_symmetry_index(sym, _roles()) == pytest.approx(0.0, abs=1e-9)
    asym = [[-1, 0, 0], [1, 0, 0], [-0.5, -1, 0.2], [0.7, -1, 0.2], [0, 0.5, 0.3]]
    k = C.op_symmetry_index(asym, _roles())
    assert k > 0.01
    half = [[c / 2 for c in p] for p in asym]
    assert C.op_symmetry_index(half, _roles()) == pytest.approx(k)
    # one pair alone is always symmetric about its own bisector: refused
    with pytest.raises(C.CombinerError, match="two mirror pairs"):
        C.op_symmetry_index(asym[:2], _roles()[:2])


def test_degenerate_inputs_and_operations_outside_the_set_are_refused():
    with pytest.raises(C.CombinerError, match="vertex"):
        C.execute("angle", [[0, 0, 0], [0, 0, 0], [1, 0, 0]])
    with pytest.raises(C.CombinerError, match="not one of"):
        C.execute("volume_of_everything", [[0, 0, 0]])
    with pytest.raises(C.CombinerError, match="inputs"):
        C.execute("distance", [[0, 0, 0]])
    with pytest.raises(C.CombinerError, match="landmark"):
        C.execute("distance", [(1.0, "m"), (2.0, "m")])
    with pytest.raises(C.CombinerError, match="unit"):
        C.execute("distance", [[0, 0, 0], [1, 0, 0]], "feet")


# ── computing a package's combiners ─────────────────────────────────────────

def test_a_computed_value_has_the_chain_of_a_measured_one(overlay):
    g, pose = _posed(overlay)
    r = C.compute(g, overlay, "stat:c_larghezza_biorbitale", "RM1", subject="US1")
    assert r.value == pytest.approx(0.084) and r.unit == "m" and r.text == "0.084 m"
    prop = g.find_node_by_id(r.property_id)
    assert prop.name == "stat:larghezza_biorbitale" and prop.value == pytest.approx(0.084)
    assert prop.data["measure"] == {"quantity": "length", "value_number": r.value, "value_unit": "m"}
    comb = g.find_node_by_id(r.combiner_id)
    assert comb.node_type == "combiner" and comb.data["em_kind"] == "stat:c_larghezza_biorbitale"
    assert comb.data["combiner"]["operation"] == "distance" and comb.data["combiner"]["digest"]
    # unit → property → combiner → the two extractors → their regions → the model
    assert _edges(g, "US1", "has_property", r.property_id)
    assert _edges(g, r.property_id, "has_data_provenance", r.combiner_id)
    ex = {e.edge_target for e in _edges(g, r.combiner_id, "combines")}
    assert ex == {X.landmark_extractor_id(pose, "exocanthion_r"), X.landmark_extractor_id(pose, "exocanthion_l")}
    for e in ex:
        region = _edges(g, e, "extracted_from")[0].edge_target
        assert _edges(g, region, "is_on_resource", "RM1")
    assert not r.warnings


def test_computing_again_updates_and_never_duplicates(overlay):
    g, _ = _posed(overlay)
    a = C.compute(g, overlay, "stat:c_larghezza_biorbitale", "RM1", subject="US1")
    n, m = len(g.nodes), len(g.edges)
    b = C.compute(g, overlay, "stat:c_larghezza_biorbitale", "RM1", subject="US1")
    assert (a.combiner_id, a.property_id) == (b.combiner_id, b.property_id)
    assert (len(g.nodes), len(g.edges)) == (n, m)
    assert a.created and not b.created and not b.changed


def test_the_type_unit_is_the_unit_shown(tmp_path):
    ov = _pkg(tmp_path, [{"id": "stat:c_bio_cm", "label": {"it": "bio", "en": "bio"}, "operation": "distance",
                          "inputs": [{"landmark": "stat:volto/exocanthion_r"}, {"landmark": "stat:volto/exocanthion_l"}],
                          "produces": "stat:larghezza_biorbitale", "unit": "cm"}])
    g, _ = _posed(ov)
    r = C.compute(g, ov, "stat:c_bio_cm", "RM1", subject="US1")
    assert (r.value, r.unit, r.text) == (pytest.approx(8.4), "cm", "8.400 cm")


def test_inputs_not_placed_are_named(overlay):
    partial = {k: v for k, v in FACE.items() if k != "exocanthion_l"}
    g, _ = _posed(overlay, partial)
    with pytest.raises(C.CombinerInputsMissing) as exc:
        C.compute(g, overlay, "stat:c_larghezza_biorbitale", "RM1", subject="US1")
    assert exc.value.missing == ["stat:volto/exocanthion_l"]
    out = C.compute_available(g, overlay, "RM1", subject="US1")
    assert [c["combiner_type"] for c in out["computed"]] == ["stat:c_altezza_facciale"]
    assert out["missing"]["stat:c_larghezza_biorbitale"] == ["stat:volto/exocanthion_l"]
    # the index waits for the width it reads
    assert out["missing"]["stat:c_indice_facciale"] == ["stat:larghezza_biorbitale"]
    assert not out["errors"]


def test_unknown_types_are_refused(overlay):
    g, _ = _posed(overlay)
    with pytest.raises(C.CombinerError, match="not a combiner type"):
        C.compute(g, overlay, "stat:c_nothing", "RM1", subject="US1")
    with pytest.raises(C.CombinerError, match="not a combiner type"):
        C.compute(g, None, "stat:c_larghezza_biorbitale", "RM1", subject="US1")


def test_a_complete_set_computes_the_three_combiners_in_order(overlay):
    """SPEC §13: «a insieme completo i tre combinatori calcolano larghezza,
    altezza e indice, ognuno con la sua catena»."""
    g, pose = _posed(overlay)
    out = C.compute_available(g, overlay, "RM1", subject="US1")
    got = {c["combiner_type"]: c for c in out["computed"]}
    assert set(got) == {"stat:c_larghezza_biorbitale", "stat:c_altezza_facciale", "stat:c_indice_facciale"}
    idx = got["stat:c_indice_facciale"]
    assert idx["value"] == pytest.approx(math.dist(FACE["nasion"], FACE["gnathion"]) / 0.084, rel=1e-4)
    assert idx["unit"] == "1" and idx["quantity"] == "ratio"
    # the ratio rests on the four points under the two distances
    ex = {e.edge_target for e in _edges(g, idx["combiner_id"], "combines")}
    assert ex == {X.landmark_extractor_id(pose, p) for p in ("exocanthion_r", "exocanthion_l", "nasion", "gnathion")}
    reads = g.find_node_by_id(idx["combiner_id"]).data["combiner"]["inputs"]
    assert [i["quale"] for i in reads] == ["stat:altezza_facciale", "stat:larghezza_biorbitale"]
    assert all(g.find_node_by_id(i["property"]) is not None for i in reads)


def test_a_quale_measured_by_hand_is_an_input_too(overlay):
    from s3dgraphy.nodes.property_node import PropertyNode
    g, _ = _posed(overlay)
    C.compute(g, overlay, "stat:c_altezza_facciale", "RM1", subject="US1")
    hand = PropertyNode("P-hand", "stat:larghezza_biorbitale", value="8.0 cm",
                        property_type="stat:larghezza_biorbitale")
    g.add_node(hand)
    g.add_edge("e-hand", "US1", "P-hand", "has_property")
    r = C.compute(g, overlay, "stat:c_indice_facciale", "RM1", subject="US1")
    assert r.value == pytest.approx(math.dist(FACE["nasion"], FACE["gnathion"]) / 0.08, rel=1e-4)


# ── recomputing ─────────────────────────────────────────────────────────────

def test_moving_a_point_recomputes_what_reads_it_and_what_reads_that(overlay):
    g, pose = _posed(overlay)
    C.compute_available(g, overlay, "RM1", subject="US1")
    moved = X.place_landmark(g, overlay, "stat:volto", "gnathion", "RM1", [0.0, -0.12, 0.002],
                             pose_id=pose, subject="US1")
    by = {g.find_node_by_id(r["combiner_id"]).data["em_kind"]: r for r in moved.recomputed}
    assert set(by) == {"stat:c_altezza_facciale", "stat:c_indice_facciale"}   # not the width
    assert by["stat:c_altezza_facciale"]["previous"] == pytest.approx(0.10002)
    assert by["stat:c_altezza_facciale"]["value"] == pytest.approx(math.dist([0, 0, 0], [0, -0.12, 0.002]), abs=1e-6)
    assert by["stat:c_indice_facciale"]["changed"]
    assert C.stale_combiners(g) == {}
    # placing it again in the same place recomputes nothing
    same = X.place_landmark(g, overlay, "stat:volto", "gnathion", "RM1", [0.0, -0.12, 0.002],
                            pose_id=pose, subject="US1")
    assert same.recomputed == []


def test_a_change_made_elsewhere_is_seen_and_recomputed(overlay):
    g, pose = _posed(overlay)
    C.compute_available(g, overlay, "RM1", subject="US1")
    # a tool moves the point with the bare reading API (no recompute there)
    ex = X.landmark_extractor_id(pose, "exocanthion_l")
    place_reading(g, ex, "RM1", {"geometry_kind": "point", "p": [0.05, -0.008, -0.012]})
    stale = C.stale_combiners(g)
    assert set(stale.values()) == {"inputs changed"} and len(stale) == 1
    out = C.recompute(g)
    assert len(out) == 2   # the width, then the index that reads it
    width = next(r for r in out if g.find_node_by_id(r["combiner_id"]).data["em_kind"] == "stat:c_larghezza_biorbitale")
    assert width["value"] == pytest.approx(0.092)
    assert C.stale_combiners(g) == {}


def test_an_input_gone_is_said_and_the_value_kept(overlay):
    g, pose = _posed(overlay)
    r = C.compute(g, overlay, "stat:c_larghezza_biorbitale", "RM1", subject="US1")
    g.remove_node(X.landmark_extractor_id(pose, "exocanthion_r"))
    assert "inputs missing" in C.stale_combiners(g)[r.combiner_id]
    out = C.recompute(g)
    assert out == [{"combiner_id": r.combiner_id, "stale": out[0]["stale"]}]
    node = g.find_node_by_id(r.combiner_id)
    assert "exocanthion_r" in node.data["combiner"]["stale"]
    assert g.find_node_by_id(r.property_id).value == pytest.approx(0.084)


def test_any_tool_recomputes_without_the_package_and_after_emjson(overlay):
    from s3dgraphy.exporter.emjson_exporter import build_emjson
    from s3dgraphy.importer.emjson_importer import parse_emjson
    g, pose = _posed(overlay)
    C.compute_available(g, overlay, "RM1", subject="US1")
    doc = json.loads(json.dumps(build_emjson(g)))
    assert "stat" in P.prefixes_used([doc["graph"]])
    back, _ = parse_emjson(doc)
    assert C.stale_combiners(back) == {}
    cid = C.combiner_id("stat:c_indice_facciale", "RM1", "US1")
    assert back.find_node_by_id(cid).data["combiner"]["operation"] == "ratio"
    prop = back.find_node_by_id(C.combined_property_id(cid))
    assert prop.data["measure"]["quantity"] == "ratio"
    # move a point in the reopened graph, with no package anywhere: recomputed
    ex = X.landmark_extractor_id(pose, "nasion")
    place_reading(back, ex, "RM1", {"geometry_kind": "point", "p": [0.0, 0.02, 0.0]})
    out = C.recompute(back)
    assert {back.find_node_by_id(r["combiner_id"]).data["em_kind"] for r in out} == \
        {"stat:c_altezza_facciale", "stat:c_indice_facciale"}
    assert all("value" in r for r in out)


def test_a_georeference_changes_no_computed_value(overlay):
    plain, _ = _posed(overlay)
    geo = _graph()
    api.declare_georeference(geo, 3844, 500000.0, 400000.0, 100.0, rotation=30.0)
    geo, _ = _posed(overlay, g=geo)
    a = C.compute_available(plain, overlay, "RM1", subject="US1")["computed"]
    b = C.compute_available(geo, overlay, "RM1", subject="US1")["computed"]
    assert [c["value"] for c in a] == [c["value"] for c in b]


def test_elevation_difference_and_area_on_placed_points(tmp_path):
    ov = _pkg(tmp_path, [
        {"id": "stat:c_dislivello", "label": {"it": "d", "en": "d"}, "operation": "elevation_difference",
         "inputs": [{"landmark": "stat:volto/glabella"}, {"landmark": "stat:volto/gnathion"}],
         "produces": "stat:dislivello", "unit": "mm"},
        {"id": "stat:c_area_occhi", "label": {"it": "a", "en": "a"}, "operation": "area_of_polygon",
         "inputs": [{"landmark": "stat:volto/exocanthion_r"}, {"landmark": "stat:volto/nasion"},
                    {"landmark": "stat:volto/exocanthion_l"}, {"landmark": "stat:volto/gnathion"}],
         "produces": "stat:area_occhi", "unit": "cm2"},
        {"id": "stat:c_simmetria", "label": {"it": "s", "en": "s"}, "operation": "symmetry_index",
         "inputs": [{"landmark": "stat:volto/exocanthion_r"}, {"landmark": "stat:volto/exocanthion_l"},
                    {"landmark": "stat:volto/nasion"}, {"landmark": "stat:volto/gnathion"}],
         "produces": "stat:simmetria"}])
    assert P.validate(tmp_path / "pkg").ok
    g, _ = _posed(ov)
    out = {c["combiner_type"]: c for c in C.compute_available(g, ov, "RM1", subject="US1")["computed"]}
    assert out["stat:c_dislivello"]["value"] == pytest.approx(112.0) and out["stat:c_dislivello"]["unit"] == "mm"
    assert out["stat:c_area_occhi"]["unit"] == "cm2" and out["stat:c_area_occhi"]["value"] > 0
    assert out["stat:c_simmetria"]["value"] == pytest.approx(0.0, abs=1e-9)


def test_a_unit_s3dgraphy_does_not_show_falls_back_and_is_said(tmp_path):
    ov = _pkg(tmp_path, [{"id": "stat:c_bio_ft", "label": {"it": "bio", "en": "bio"}, "operation": "distance",
                          "inputs": [{"landmark": "stat:volto/exocanthion_r"}, {"landmark": "stat:volto/exocanthion_l"}],
                          "produces": "stat:larghezza_biorbitale", "unit": "ft"}])
    g, _ = _posed(ov)
    r = C.compute(g, ov, "stat:c_bio_ft", "RM1", subject="US1")
    assert (r.value, r.unit) == (pytest.approx(0.084), "m")
    assert any("'ft'" in w for w in r.warnings)
