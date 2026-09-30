"""MICRO-CATTURA-MURATURE, parte 1 — la cattura è un'acquisizione.

L'asse `acquisition` di `dtc_kinds` ha due famiglie (em_visual_rules 1.6.22):
`capture` e `retrieval`. Nessun tipo di nodo nuovo. La forma definitiva del
timbro è `how.dtc_kind = <cattura>`; la provvisoria di EMStudio
(`local_import` + `how.acquisition.capture`) si legge ancora; un timbro vecchio
con la cattura come genere — quando le catture stavano sull'asse `input` — si
apre.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DTCAcquisitionNode, ResourceNode
from s3dgraphy.dtc.ingest import bucket_acquisition
from s3dgraphy.stamp.absorb import absorb_stamp
from s3dgraphy.stamp.emit import emit_stamp
from s3dgraphy.utils.utils import get_dtc_kind_family, get_dtc_kinds
from dtcstamp import clean_stamp

RULES = (Path(__file__).resolve().parents[1] / "src" / "s3dgraphy"
         / "JSON_config" / "em_visual_rules.json")
SHA = "sha256:" + "c" * 64
CAPTURES = ("photo", "laserscanner", "topographic", "gnss_survey",
            "field_drawing", "recording_sheet")
RETRIEVALS = ("download", "local_import", "uri_reference", "ingest")


def _graph_with_a_file(graph_id="g"):
    g = Graph(graph_id=graph_id)
    g.add_node(ResourceNode("res:a", name="IMG_0001.JPG", checksum=SHA))
    return g


def _origin_stamp(**how):
    return {"stamp": 1,
            "self": {"resource_id": "res:a", "digest": SHA,
                     "digest_covers": "artifact"},
            "from": [],
            "how": {"process_id": "acq:volo", **how},
            "by": {"at": "2026-03-14T09:00:00Z"}}


def _only_acquisition(graph):
    events = [n for n in graph.nodes
              if n.node_type in ("dtc_acquisition", "dtc_process")]
    assert len(events) == 1, [(n.node_type, n.node_id) for n in events]
    return events[0]


# ── il vocabolario ──────────────────────────────────────────────────────────

def test_the_acquisition_axis_has_two_families_and_nothing_else():
    kinds = get_dtc_kinds()["acquisition"]
    assert set(kinds) == set(CAPTURES) | set(RETRIEVALS)
    for k in CAPTURES:
        assert get_dtc_kind_family(k) == "capture", k
    for k in RETRIEVALS:
        assert get_dtc_kind_family(k) == "retrieval", k


def test_input_is_a_read_alias_with_no_entries_of_its_own():
    """Letto da qui dà le catture di sempre; letto dal JSON non ha voci — così
    una tavolozza che cammina gli assi non disegna ogni cattura due volte."""
    assert set(get_dtc_kinds()["input"]) == set(CAPTURES)
    raw = json.loads(RULES.read_text(encoding="utf-8"))["dtc_kinds"]["input"]
    assert [k for k in raw if not k.startswith("_")] == []
    assert raw["_alias_of"] == {"axis": "acquisition", "family": "capture"}


def test_no_kind_lives_on_two_axes():
    raw = json.loads(RULES.read_text(encoding="utf-8"))["dtc_kinds"]
    seen = {}
    for axis, entries in raw.items():
        if axis.startswith("_"):
            continue
        for kind in entries:
            if kind.startswith("_"):
                continue
            assert kind not in seen, f"{kind} on {seen.get(kind)} and {axis}"
            seen[kind] = axis


def test_the_missing_processes_are_there():
    process = get_dtc_kinds()["process"]
    for k in ("photogrammetry", "transformation", "decimation", "georeferencing",
              "format_conversion", "classification", "vectorization"):
        assert k in process, k


def test_the_new_kinds_are_translated_in_it_and_de():
    from s3dgraphy.tools.datamodel_i18n import dtc_kind_label

    assert dtc_kind_label("photo", "it") == "Fotografia"
    assert dtc_kind_label("recording_sheet", "it") == "Scheda compilata"
    assert dtc_kind_label("format_conversion", "it") == "Trasformazione di formato"
    assert dtc_kind_label("gnss_survey", "de") == "GNSS-Vermessung"
    assert dtc_kind_label("family_capture", "it") == "Cattura"
    for k in CAPTURES + RETRIEVALS + ("decimation", "georeferencing",
                                      "format_conversion", "classification",
                                      "vectorization"):
        for lang in ("en", "it", "de"):
            assert dtc_kind_label(k, lang), (k, lang)


# ── 1 · un timbro «Fotografia» su un'origine ────────────────────────────────

@pytest.mark.parametrize("kind", CAPTURES)
def test_a_capture_is_a_valid_acquisition_kind(kind):
    node = DTCAcquisitionNode("acq:x", dtc_kind=kind)
    assert node.data["dtc_kind"] == kind


def test_a_photograph_stamp_on_an_origin_makes_a_valid_acquisition():
    g = _graph_with_a_file()
    bucket_acquisition(g, ["res:a"], name="Volo 2026-03", dtc_kind="photo",
                       metadata={"camera": "DJI Mavic 3E"},
                       at="2026-03-14T09:00:00Z")
    stamp = clean_stamp(emit_stamp(g, "res:a"))
    assert stamp["from"] == []
    assert stamp["how"]["dtc_kind"] == "photo"
    assert stamp["how"]["acquisition"] == {"camera": "DJI Mavic 3E"}

    fresh = Graph(graph_id="h")
    result = absorb_stamp(fresh, stamp)
    assert result.applied and not result.disagreements
    event = _only_acquisition(fresh)
    assert isinstance(event, DTCAcquisitionNode)
    assert event.data["dtc_kind"] == "photo"
    # e riemesso dice la stessa cosa: il secondo riassorbimento è un duplicato
    again = absorb_stamp(fresh, stamp)
    assert again.deduplicated, again.disagreements
    assert clean_stamp(emit_stamp(fresh, "res:a"))["how"] == stamp["how"]


def test_a_retrieval_origin_comes_back_as_an_acquisition_not_a_transformation():
    """Il difetto misurato: prima tornava `DTCProcessNode` «transformation», e il
    secondo riassorbimento dello stesso timbro era in disaccordo con il primo."""
    g = _graph_with_a_file()
    bucket_acquisition(g, ["res:a"], name="dep", dtc_kind="ingest",
                       at="2026-03-14T09:00:00Z")
    stamp = clean_stamp(emit_stamp(g, "res:a"))
    fresh = Graph(graph_id="h")
    absorb_stamp(fresh, stamp)
    event = _only_acquisition(fresh)
    assert event.node_type == "dtc_acquisition"
    assert event.data["dtc_kind"] == "ingest"
    assert absorb_stamp(fresh, stamp).deduplicated


# ── 2 · il sidecar provvisorio si rilegge ───────────────────────────────────

def test_the_provisional_sidecar_reads_as_the_capture():
    stamp = _origin_stamp(dtc_kind="local_import",
                          acquisition={"capture": "photo", "lens": "24mm"})
    fresh = Graph(graph_id="h")
    result = absorb_stamp(fresh, stamp)
    assert result.applied
    event = _only_acquisition(fresh)
    assert event.node_type == "dtc_acquisition"
    assert event.data["dtc_kind"] == "photo"
    how = clean_stamp(emit_stamp(fresh, "res:a"))["how"]
    assert how["dtc_kind"] == "photo"
    assert how["acquisition"] == {"lens": "24mm"}, "la cattura non resta ANCHE lì"
    # il provvisorio e il definitivo dello stesso atto non sono in disaccordo
    assert absorb_stamp(fresh, stamp).deduplicated


def test_a_graph_in_the_provisional_form_emits_the_definitive_one():
    """È la strada del bridge di oggi: `local_import` più `metadata.capture`."""
    g = _graph_with_a_file()
    bucket_acquisition(g, ["res:a"], name="Volo", dtc_kind="local_import",
                       metadata={"capture": "laserscanner"},
                       at="2026-03-14T09:00:00Z")
    how = clean_stamp(emit_stamp(g, "res:a"))["how"]
    assert how["dtc_kind"] == "laserscanner"
    assert "acquisition" not in how


def test_a_stated_retrieval_beside_a_capture_is_not_overwritten():
    """`local_import` lo metteva il bridge; `download` l'ha detto qualcuno."""
    stamp = _origin_stamp(dtc_kind="download", acquisition={"capture": "photo"})
    fresh = Graph(graph_id="h")
    absorb_stamp(fresh, stamp)
    event = _only_acquisition(fresh)
    assert event.data["dtc_kind"] == "download"
    assert clean_stamp(emit_stamp(fresh, "res:a"))["how"]["acquisition"] == {
        "capture": "photo"}


def test_an_emjson_in_the_provisional_form_opens_as_the_capture():
    from s3dgraphy import api

    doc = {"header": {"format": "em.json", "version": "1.0"},
           "graph": {"graph_id": "g", "nodes": [
               {"id": "res:a", "node_type": "resource", "name": "x.jpg",
                "data": {"checksum": SHA}},
               {"id": "acq:1", "node_type": "dtc_acquisition", "name": "Volo",
                "data": {"dtc_kind": "local_import", "capture": "photo"}}],
               "edges": [{"id": "e1", "source": "acq:1", "target": "res:a",
                          "edge_type": "dtc_had_output"}]}}
    graph, _ = api.load_emjson(doc)
    node = graph.find_node_by_id("acq:1")
    assert node.data["dtc_kind"] == "photo"
    assert "capture" not in node.data


# ── 3 · un vecchio sidecar con la cattura sotto `input` si apre ─────────────

def test_an_old_sidecar_with_an_input_capture_as_its_kind_opens():
    """Prima del 1.6.22 `laserscanner` era un genere dell'asse `input`: un timbro
    che lo portava come genere rientrava come «transformation». Ora è la cattura
    che era, con la stessa chiave."""
    stamp = _origin_stamp(dtc_kind="laserscanner")
    fresh = Graph(graph_id="h")
    assert absorb_stamp(fresh, stamp).applied
    event = _only_acquisition(fresh)
    assert event.node_type == "dtc_acquisition"
    assert event.data["dtc_kind"] == "laserscanner"


def test_an_old_resource_with_an_input_kind_still_opens_and_resolves():
    """Una Resource con `data.dtc_kind = "photo"` (ruolo di ingresso): il genere
    si legge e non si valida, e la chiave è la stessa di prima."""
    from s3dgraphy import api

    doc = {"header": {"format": "em.json", "version": "1.0"},
           "graph": {"graph_id": "g", "nodes": [
               {"id": "in1", "node_type": "resource", "name": "p.jpg",
                "data": {"dtc_kind": "photo"}}], "edges": []}}
    graph, _ = api.load_emjson(doc)
    assert graph.find_node_by_id("in1").data["dtc_kind"] == "photo"
    assert "photo" in get_dtc_kinds()["input"]
    assert get_dtc_kind_family("photo") == "capture"


def test_an_acquisition_kind_with_parents_stays_a_process():
    """Un'acquisizione con degli ingressi non è un'origine: resta il ramo di
    sempre, e il genere cade sul default."""
    stamp = _origin_stamp(dtc_kind="photo")
    stamp["from"] = [{"resource_id": "res:p", "digest": "sha256:" + "d" * 64}]
    fresh = Graph(graph_id="h")
    absorb_stamp(fresh, stamp)
    event = _only_acquisition(fresh)
    assert event.node_type == "dtc_process"
    assert event.data["dtc_kind"] == "transformation"
