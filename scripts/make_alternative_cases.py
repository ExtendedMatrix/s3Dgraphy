"""Write JSON_config/alternative_cases.json — the cases of the alternatives
(E.D. 17 Oct 2026, «lo stesso cappello») every copy of the rule passes:
s3Dgraphy (tests/test_alternative_sets.py), EMStudio (check-alternatives.mjs),
Heriverse (tests/check-alternatives.mjs).

Each case: a small graph (the ``graph`` section of an em.json: nodes and
edges), the sets ``alternative_sets`` gives (flattened, containers before
their members: hat, hat_kind, parent, alternatives with their reason, reasons,
covers, coverage), the codes of the warnings, and choices (``use``, optional
``force``) with the level and the id chosen. The expected values are written
by the reference implementation and read by a person before commit.

    .venv/bin/python scripts/make_alternative_cases.py
"""
import json
from pathlib import Path

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.epoch_node import EpochNode
from s3dgraphy.nodes.group_node import RepresentationModelNodeGroup
from s3dgraphy.nodes.representation_node import RepresentationModelNode
from s3dgraphy.resources.alternatives import alternative_sets, choose_alternative, find_set, iter_sets

OUT = Path(__file__).resolve().parents[1] / "src" / "s3dgraphy" / "JSON_config" / "alternative_cases.json"
VIEWER = ["heriverse", "aton", "web", "realtime"]


def sha(c):
    return "sha256:" + c * 64


def mesh(g, name, c, epoch="ep", uses=(("lod0", ["analysis"]), ("lod1", ["aton", "heriverse"]))):
    rid = f"{name}.master"
    api.add_resource(g, resource_id=rid, name=name, kind="3d_model", tier="master",
                     files=[{"path": f"{name}.glb", "checksum": sha(c)}])
    prev = rid
    for i, (lvl, use) in enumerate(uses):
        v = api.add_version(g, prev, level=lvl, use=use, version_id=f"{name}.{lvl}",
                            files=[{"path": f"{lvl}/{name}.glb", "checksum": sha(c)[:-2] + f"{i}{i}"}])
        prev = v["version_id"]
    g.add_node(RepresentationModelNode(f"{name}_model", name=name))
    g.add_edge(f"{name}_model_has_linked_resource_{rid}", f"{name}_model", rid, "has_linked_resource")
    g.add_edge(f"{epoch}_has_representation_model_{name}_model", epoch, f"{name}_model",
               "has_representation_model")
    return f"{name}_model"


def tileset(g, hat, uses=("web", "realtime")):
    api.add_resource(g, resource_id="tiles.master", name="Survey tileset", kind="3d_model",
                     tier="master", files=[{"path": "survey.zip", "checksum": sha("f"),
                                            "media_type": "application/zip"}])
    api.add_version(g, "tiles.master", level="lod0", use=list(uses), version_id="tiles.lod0",
                    files=[{"path": "survey/tileset.json", "checksum": sha("e"),
                            "media_type": "application/json"}])
    g.find_node_by_id("tiles.lod0").data["packaging"] = "directory"
    g.find_node_by_id("tiles.lod0").data["geometric_error_m"] = 6.144
    g.add_edge(f"{hat}_has_linked_resource_tiles.master", hat, "tiles.master", "has_linked_resource")


def base(n=4, container=True):
    g = Graph("alt")
    g.add_node(EpochNode("ep", name="XX sec", start_time=1900, end_time=2000))
    models = [mesh(g, f"EST_{i}", "0123456789"[i]) for i in range(n)]
    if container:
        g.add_node(RepresentationModelNodeGroup("survey_rmgroup", name="Survey 2015", description=""))
        for m in models:
            g.add_edge(f"{m}_is_in_representation_model_group_survey_rmgroup", m, "survey_rmgroup",
                       "is_in_representation_model_group")
    return g, models


def tileset_rm(g, epoch="ep"):
    g.add_node(RepresentationModelNode("XX_tileset_model", name="XX_tileset"))
    g.add_edge(f"{epoch}_has_representation_model_XX_tileset_model", epoch, "XX_tileset_model",
               "has_representation_model")
    return "XX_tileset_model"


def section(g):
    doc = api.graph_to_emjson(g)
    sec = doc.get("graph") or next(iter(doc["graphs"].values()))
    nodes = [{k: n[k] for k in ("id", "node_type", "name", "data") if k in n}
             for n in sec["nodes"] if n["node_type"] != "geo_position"]
    for n in nodes:
        n["data"] = {k: v for k, v in (n.get("data") or {}).items()
                     if k in ("url", "url_type", "tier", "media_type", "packaging", "use",
                              "geometric_error_m", "size_bytes", "dtc_kind", "parameters")}
    edges = [{k: e[k] for k in ("id", "source", "target", "edge_type")} for e in sec["edges"]]
    return {"nodes": nodes, "edges": edges}


def expect(g, choices):
    res = alternative_sets(g)
    sets = [{"hat": s["hat"], "hat_kind": s["hat_kind"], "parent": s["parent"],
             "alternatives": [[x["id"], x["reason"]] for x in s["alternatives"]],
             "reasons": s["reasons"], "covers": s["covers"], "coverage": s["coverage"]}
            for s in iter_sets(res)]
    out_choices = []
    for c in choices:
        s = find_set(res, c["hat"])
        ch = choose_alternative(s, c["use"], force=c.get("force"))
        item = {**c, "expect": {"level": ch["level"], "id": (ch["entry"] or {}).get("id"),
                                "use": ch["use"]}}
        if ch["members"]:
            item["expect"]["members"] = {h: (m["entry"] or {}).get("id")
                                         for h, m in ch["members"].items()}
        out_choices.append(item)
    return {"sets": sets, "warnings": sorted(w["code"] for w in res["warnings"]),
            "counts": res["counts"]}, out_choices


def case(name, g, choices):
    exp, ch = expect(g, choices)
    return {"name": name, "graph": section(g), "expect": exp, "choices": ch}


def main():
    cases = []
    g, models = base()
    tileset(g, "survey_rmgroup")
    cases.append(case("a container of 4 meshes and a tileset hatted by the container", g, [
        {"hat": "survey_rmgroup", "use": VIEWER},
        {"hat": "survey_rmgroup", "use": ["web", "realtime"]},
        {"hat": "survey_rmgroup", "use": ["web"], "force": "members"},
        {"hat": "survey_rmgroup", "use": ["analysis"], "force": "container"},
        {"hat": "survey_rmgroup", "use": ["print"]},
        {"hat": "survey_rmgroup", "use": ["analysis"]},
        {"hat": "EST_0_model", "use": VIEWER}]))

    g, models = base()
    rm = tileset_rm(g)
    tileset(g, rm)
    g.add_edge(f"{rm}_is_in_representation_model_group_survey_rmgroup", rm, "survey_rmgroup",
               "is_in_representation_model_group")
    cases.append(case("a tileset member of a container: an RM among the others", g, [
        {"hat": "survey_rmgroup", "use": VIEWER},
        {"hat": rm, "use": VIEWER}]))

    g, models = base()
    rm = tileset_rm(g)
    tileset(g, rm)
    g.add_edge("survey_rmgroup_has_linked_resource_tiles.master", "survey_rmgroup", "tiles.master",
               "has_linked_resource")
    cases.append(case("a tileset with two hats, the container and an RM of its own: warning", g, []))

    g, models = base(n=2, container=False)
    g.add_node(EpochNode("ep2", name="II AD", start_time=100, end_time=200))
    g.add_node(RepresentationModelNode("copy_model", name="EST_0 copy"))
    g.add_edge("copy_model_has_linked_resource_EST_0.lod1", "copy_model", "EST_0.lod1",
               "has_linked_resource")
    g.add_edge("ep2_has_representation_model_copy_model", "ep2", "copy_model",
               "has_representation_model")
    cases.append(case("a version linked again in another epoch: two alternatives of one hat in two epochs", g, []))

    g, models = base(n=3, container=False)
    cases.append(case("three RMs without a container: one set each, fidelity and lod", g, [
        {"hat": "EST_1_model", "use": ["web", "realtime"]},
        {"hat": "EST_1_model", "use": VIEWER}]))

    doc = {"_version": "1.0.0",
           "_note": ("The alternatives of a 3D object (E.D., 17 Oct 2026, «lo stesso cappello»): two resources "
                     "are alternatives if and only if they have the same hat (has_linked_resource from an RM "
                     "or an RM container to their asset). ONE rule, s3dgraphy.resources.alternatives "
                     "(alternative_sets, choose_alternative), described by em_visual_rules.json → "
                     "alternatives and copied by the clients that cannot call Python (EMStudio, Heriverse); "
                     "every copy passes these cases. graph: nodes and edges as an em.json graph section "
                     "carries them. expect.sets: every set, containers before their members (hat, hat_kind, "
                     "parent, alternatives as [id, reason], reasons, covers, coverage); expect.warnings: the "
                     "codes; choices: use (tried in order), force (container | members), and the level, the "
                     "id and the use chosen (members: the id each member lights). Written by "
                     "scripts/make_alternative_cases.py."),
           "cases": cases}
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT}: {len(cases)} cases")


if __name__ == "__main__":
    main()
