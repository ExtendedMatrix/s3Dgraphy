"""DP-79 P4 — the notebook export: the fourth output, and the live one.

The others freeze the embeds; this one turns them into questions the reader
runs. So what is asserted here is not "it produced a file" but the two
properties that make it worth having:

* it is a **valid notebook** and it **executes** — measured with nbclient when
  the notebook stack is installed, skipped by name when it is not;
* it carries **no copy of the graph**. A notebook with the answers baked in
  would be a snapshot wearing a notebook's clothes, and the snapshot already
  exists in three formats.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                       # noqa: E402
from s3dgraphy.graph import Graph                               # noqa: E402
from s3dgraphy.nodes import StratigraphicUnit                   # noqa: E402
from s3dgraphy.nodes.epoch_node import EpochNode                # noqa: E402
from s3dgraphy.nodes.narrative_node import NarrativeNode        # noqa: E402


def _study():
    graph = Graph(graph_id="portico")
    graph.add_node(EpochNode(node_id="ep-1", name="Fase 1",
                             start_time=1200, end_time=1450))
    graph.add_node(StratigraphicUnit("us1", name="US 1"))
    graph.add_edge("e1", "us1", "ep-1", "has_first_epoch")
    graph.add_node(NarrativeNode.from_payload("narr-1", "Il portico", data={
        "chapters": [{"title": "Le fasi", "blocks": [
            {"block_type": "prose", "text": "Il muro è in opus mixtum."},
            {"block_type": "embed", "ref": "us1", "view_type": "us"},
            {"block_type": "embed", "ref": "ep-1", "view_type": "matrix"},
            {"block_type": "embed", "ref": "rm-1", "view_type": "scene3d"},
            {"block_type": "prose", "text": "Bozza.", "ai_generated": True},
        ]}]}))
    return graph


@pytest.fixture()
def study():
    return _study()


def test_it_is_a_valid_notebook(study):
    nb = json.loads(api.export_narrative_ipynb(study, "narr-1"))
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    assert nb["metadata"]["stratigraph"]["narrative_id"] == "narr-1"
    kinds = [c["cell_type"] for c in nb["cells"]]
    assert "markdown" in kinds and "code" in kinds
    assert all(c.get("id") for c in nb["cells"]), "nbformat 4.5 wants cell ids"


def test_the_prose_becomes_markdown_and_the_embeds_become_queries(study):
    nb = json.loads(api.export_narrative_ipynb(study, "narr-1"))
    text = json.dumps(nb)
    assert "opus mixtum" in text, "the prose is there"
    assert "narratives_citing" in text, "a unit embed asks where it is cited"
    assert "interpretive_coverage" in text or "units_per_epoch" in text
    # the 3D one is a LINK, not a figure: a scene is navigated, not plotted
    scene = [c for c in nb["cells"] if "3D scene is navigated" in "".join(c["source"])]
    assert len(scene) == 1
    assert scene[0]["cell_type"] == "markdown"


def test_it_carries_no_copy_of_the_graph(study):
    """The property that makes it LIVE. A notebook holding the nodes would be a
    snapshot, and we already have three of those."""
    nb = api.export_narrative_ipynb(study, "narr-1")
    assert "opus mixtum" in nb, "the author's prose travels…"
    assert '"node_type"' not in nb, "…but the graph does not"
    assert "has_first_epoch" not in nb


def test_an_unvalidated_draft_is_left_out_or_says_so_in_the_text(study):
    """What no person validated is not printed (E.D., 29 Sep 2026); forced in,
    it says so in the text — a notebook gets copied, and a badge does not
    survive copying."""
    assert api.narrative_unvalidated(study, "narr-1"), "the fixture has one"
    nb = api.export_narrative_ipynb(study, "narr-1")
    assert "non validato da una persona" not in nb
    forced = api.export_narrative_ipynb(study, "narr-1", include_unvalidated=True)
    assert "⚠︎ non validato da una persona" in forced


def test_the_loader_cell_can_be_pointed_at_a_url(study):
    nb = api.export_narrative_ipynb(study, "narr-1",
                                    emjson_url="https://x/catalog/study/y/emjson")
    assert "https://x/catalog/study/y/emjson" in nb
    assert "urllib.request" in nb, "a URL source is fetched, not assumed local"


def test_it_is_deterministic(study):
    assert api.export_narrative_ipynb(study, "narr-1") \
        == api.export_narrative_ipynb(_study(), "narr-1")


def test_an_unknown_narrative_is_a_KeyError(study):
    with pytest.raises(KeyError):
        api.export_narrative_ipynb(study, "narr-nope")


# ── the proof that matters: it RUNS ─────────────────────────────────────────

def test_the_notebook_executes_headless(study, tmp_path):
    """Run every cell, fail on the first that raises.

    A notebook is code nobody compiles: it rots silently, and the first person
    to notice is whoever opens it in front of an audience.
    """
    nbformat = pytest.importorskip("nbformat", reason="needs the notebook stack")
    pytest.importorskip("nbclient", reason="needs the notebook stack")
    pytest.importorskip("ipykernel", reason="needs the notebook stack")
    from nbclient import NotebookClient

    # a real container on disk, so the run needs no network
    from s3dgraphy.container import container_of, save_container_file
    source = tmp_path / "study.em.json"
    save_container_file(container_of(study), str(source))

    path = tmp_path / "narrative.ipynb"
    path.write_text(api.export_narrative_ipynb(study, "narr-1",
                                               emjson_url=str(source)),
                    encoding="utf-8")

    nb = nbformat.read(str(path), as_version=4)
    NotebookClient(nb, timeout=120, kernel_name="python3").execute()

    errors = [o for cell in nb.cells for o in (cell.get("outputs") or [])
              if o.get("output_type") == "error"]
    assert not errors, f"{len(errors)} cell(s) raised: " + \
        "; ".join(f"{e.get('ename')}: {e.get('evalue')}" for e in errors[:3])

    # …and a cell really produced something FROM the graph
    streams = "".join(o.get("text", "") for cell in nb.cells
                      for o in (cell.get("outputs") or [])
                      if o.get("output_type") == "stream")
    assert "nodes" in streams and "edges" in streams
    assert "citations" in streams
