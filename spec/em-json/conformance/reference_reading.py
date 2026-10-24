"""The REFERENCE READING of an em.json file — what a conforming reader obtains.

Pure standard library, independent of any implementation (s3Dgraphy included):
it applies the reading rules of the specification (SPEC.md, section 3) to a
document and returns a small summary, the same for every conforming reader:

    {"form": "container" | "flat",
     "active_graph_id": "...",
     "graphs": {"<graph id>": {
         "role": "study" | "shelf" | "dtc" | "periodizations",
         "nodes": {"<id>": "<node_type>"},
         "edges": {"<id>": ["<edge_type>", "<source>", "<target>"]},
         "links": {"<id>": ["<edge_type>", "<source>", "<graph id>", "<node id>"]}}}}

Run it to (re)write the expected results beside the samples::

    python reference_reading.py            # writes expected/<name>.json
    python reference_reading.py --check    # compares, exits 1 on a difference

CC0 1.0 — like the schemas and the samples, free to copy into any implementation.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ROLES = {"ShelfGraph": "shelf", "DTCCorpus": "dtc", "Periodizations": "periodizations"}

#: Keys that a writer MUST carry through a round trip in these samples (§4.5:
#: the header keys it does not own; the node's data; the edge's attributes).
MUST_SURVIVE = {
    "06-unknown-keys.em.json": [
        ["header", "x-lab"],
        ["graphs", "GT16", "nodes", "us1", "data", "x-field"],
        ["graphs", "GT16", "edges", "e1", "attributes", "x-certainty"],
    ],
}


def _members(doc):
    if isinstance(doc.get("graphs"), dict):
        return "container", doc["graphs"]
    graph = doc.get("graph") or {}
    return "flat", {str(graph.get("graph_id") or "graph"): graph}


def reading(doc):
    form, members = _members(doc)
    graphs = {}
    for member_id, section in members.items():
        if not isinstance(section, dict):
            continue                                    # reported, not fatal
        gid = str(section.get("graph_id") or member_id)
        marker = (section.get("data") or {}).get("em_collection")
        graphs[gid] = {
            "role": ROLES.get(marker, "study"),         # unknown marker: a graph
            "nodes": {str(n["id"]): str(n["node_type"])
                      for n in section.get("nodes") or []
                      if isinstance(n, dict) and "id" in n and "node_type" in n},
            "edges": {str(e["id"]): [e["edge_type"], e["source"], e["target"]]
                      for e in section.get("edges") or []
                      if isinstance(e, dict) and "id" in e},
            "links": {str(l["id"]): [l["edge_type"], l["source"],
                                     l["target"]["graph_id"], l["target"]["node_id"]]
                      for l in section.get("links") or []
                      if isinstance(l, dict) and isinstance(l.get("target"), dict)},
        }
    studies = [g for g, v in graphs.items() if v["role"] == "study"]
    active = doc.get("active_graph_id") if form == "container" else (studies or [None])[0]
    if active not in studies:
        active = studies[0] if studies else None       # reported, then the first
    return {"form": form, "active_graph_id": active, "graphs": graphs}


def expected_for(path):
    out = reading(json.loads(Path(path).read_text(encoding="utf-8")))
    out["schema"] = "em.v1.schema.json" if out["form"] == "flat" else "em.v1.1.schema.json"
    out["must_survive_round_trip"] = MUST_SURVIVE.get(Path(path).name, [])
    return out


def main(argv):
    check = "--check" in argv
    bad = 0
    for sample in sorted(HERE.glob("*.em.json")):
        target = HERE / "expected" / (sample.name[:-len(".em.json")] + ".json")
        text = json.dumps(expected_for(sample), indent=2, ensure_ascii=False) + "\n"
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                print(f"differs: {target.name}")
                bad += 1
        else:
            target.parent.mkdir(exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target.relative_to(HERE)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
