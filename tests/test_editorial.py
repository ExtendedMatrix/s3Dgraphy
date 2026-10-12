"""Editorial stamps — the last hand on a node (AUDIT1).

Four claims:

  E1  the stamps are AUTOMATIC and nothing is invented: no identity, no author;
      creation is recorded once and an edit overwrites only the modification.
  E2  they survive the em.json round-trip (they are data, not a UI state).
  E3  they project as PROV-O and come back — created/modified told apart.
  E4  they do not disturb what already exists: a legacy node has none, and a
      graph carrying them is still isomorphic through RDF.
"""

import json
from pathlib import Path

import pytest

from s3dgraphy import api
from s3dgraphy.editorial import (
    FIELDS,
    clear_stamps,
    normalize_orcid,
    now_iso,
    read_stamps,
    stamp_created,
    stamp_modified,
)
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import StratigraphicUnit

# ORCID's own documented example iD (valid MOD-11-2 checksum).
ORCID = "0000-0002-1825-0097"
OTHER = "0000-0001-5109-3700"


def _unit(node_id="US1") -> StratigraphicUnit:
    return StratigraphicUnit(node_id, name=node_id)


# ── E1 · automatic, and never invented ──────────────────────────────────────

def test_e1_creation_stamps_the_identity_and_the_clock():
    node = _unit()
    stamps = stamp_created(node, by=ORCID)
    assert stamps["created_by"] == ORCID
    assert stamps["created_at"].endswith("Z")
    # nothing else: a node that was just made has not been modified
    assert "modified_by" not in stamps and "modified_at" not in stamps


def test_e1_without_an_identity_no_author_is_invented():
    """The whole point of "absent means unknown". A stamp that filled in
    "unknown" would be a record of something nobody said."""
    node = _unit()
    stamps = stamp_created(node)
    assert "created_by" not in stamps
    assert stamps["created_at"]          # the clock is always knowable
    stamps = stamp_modified(node)
    assert "modified_by" not in stamps
    assert stamps["modified_at"]


def test_e1_creation_is_recorded_once():
    node = _unit()
    first = stamp_created(node, by=ORCID, at="2026-01-01T00:00:00Z")
    stamp_created(node, by=OTHER, at="2026-08-13T10:00:00Z")
    assert read_stamps(node)["created_by"] == first["created_by"] == ORCID
    assert read_stamps(node)["created_at"] == "2026-01-01T00:00:00Z"


def test_e1_an_edit_overwrites_only_the_last_hand():
    node = _unit()
    stamp_created(node, by=ORCID, at="2026-01-01T00:00:00Z")
    stamp_modified(node, by=OTHER, at="2026-02-02T00:00:00Z")
    stamp_modified(node, by=ORCID, at="2026-03-03T00:00:00Z")
    s = read_stamps(node)
    assert (s["created_by"], s["created_at"]) == (ORCID, "2026-01-01T00:00:00Z")
    # LAST hand, not a history: the middle edit is gone, and that is the design
    assert (s["modified_by"], s["modified_at"]) == (ORCID, "2026-03-03T00:00:00Z")


def test_e1_an_orcid_url_is_the_same_identity():
    assert normalize_orcid(f"https://orcid.org/{ORCID}") == ORCID
    assert normalize_orcid(f"  {ORCID.lower()} ") == ORCID
    # a different number of digits is a different identifier, not this one
    assert normalize_orcid("0000-0002-1825") is None
    assert normalize_orcid(None) is None


def test_e1_now_is_utc_to_the_second():
    stamp = now_iso()
    assert stamp.endswith("Z") and "." not in stamp
    assert len(stamp) == len("2026-08-13T21:04:05Z")


def test_e1_clearing_removes_all_four():
    node = _unit()
    stamp_created(node, by=ORCID)
    stamp_modified(node, by=OTHER)
    clear_stamps(node)
    assert read_stamps(node) == {}
    # keeping the times without the names would still say when someone was at
    # their desk — so all four go
    assert not any(k in node.data for k in FIELDS)


# ── E2 · they are data ──────────────────────────────────────────────────────

def test_e2_stamps_survive_the_emjson_round_trip(tmp_path):
    g = Graph(graph_id="audit_demo")
    node = _unit()
    stamp_created(node, by=ORCID, at="2026-01-01T00:00:00Z")
    stamp_modified(node, by=OTHER, at="2026-02-02T00:00:00Z")
    g.add_node(node)

    path = tmp_path / "audit.em.json"
    from s3dgraphy.exporter.emjson_exporter import export_emjson
    export_emjson(g, str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    member = payload["graphs"]["audit_demo"]
    stored = next(n for n in member["nodes"] if n["id"] == "US1")["data"]
    assert stored["created_by"] == ORCID
    assert stored["modified_at"] == "2026-02-02T00:00:00Z"

    back, warnings = api.load_emjson_file(str(path))
    assert read_stamps(back.find_node_by_id("US1")) == {
        "created_by": ORCID, "created_at": "2026-01-01T00:00:00Z",
        "modified_by": OTHER, "modified_at": "2026-02-02T00:00:00Z",
    }


def test_e2_a_legacy_node_carries_nothing():
    """Every node written before today. Absent is not false."""
    assert read_stamps(_unit()) == {}


# ── E3 · the PROV-O projection ──────────────────────────────────────────────

rdflib = pytest.importorskip("rdflib")
from rdflib.compare import isomorphic, to_isomorphic  # noqa: E402

from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402

EM_NS = "https://w3id.org/em/ontology#"
PROV_NS = "http://www.w3.org/ns/prov#"
DCT_NS = "http://purl.org/dc/terms/"


def _stamped_graph() -> Graph:
    g = Graph(graph_id="audit_rdf")
    node = _unit()
    stamp_created(node, by=ORCID, at="2026-01-01T00:00:00Z")
    stamp_modified(node, by=OTHER, at="2026-02-02T00:00:00Z")
    g.add_node(node)
    return g


def _export(graph: Graph, path: Path) -> str:
    return RDFExporter(str(path), format="turtle").export_single_graph(graph)


def _rdf(path: str):
    g = rdflib.Graph()
    g.parse(path, format="turtle")
    return g


def test_e3_the_stamps_project_as_prov(tmp_path):
    ttl = _export(_stamped_graph(), tmp_path / "a.ttl")
    triples = _rdf(ttl)
    subject = next(s for s in triples.subjects() if str(s).endswith("/node/US1"))

    def objects(pred):
        return {str(o) for o in triples.objects(subject, rdflib.URIRef(pred))}

    # the editorial author is an ORCID IRI — an iD IS a URL, nothing is minted
    assert objects(EM_NS + "createdBy") == {f"https://orcid.org/{ORCID}"}
    # …and a PROV reader that never heard of em: gets the attribution anyway
    assert objects(PROV_NS + "wasAttributedTo") == {f"https://orcid.org/{ORCID}"}
    assert objects(EM_NS + "lastEditedBy") == {f"https://orcid.org/{OTHER}"}
    # The instants come out spelled `+00:00`: rdflib normalises an xsd:dateTime
    # through a Python datetime, and `Z` and `+00:00` are the same instant in
    # XSD. Compared as instants, therefore — and the property graph gets its own
    # canonical `Z` back on import (`normalize_instant`), so the file does not
    # come home reworded.
    assert objects(PROV_NS + "generatedAtTime") == {"2026-01-01T00:00:00+00:00"}
    assert objects(EM_NS + "modifiedAt") == {"2026-02-02T00:00:00+00:00"}
    assert objects(DCT_NS + "modified") == {"2026-02-02T00:00:00+00:00"}


def test_e3_an_unstamped_node_says_nothing(tmp_path):
    """No triple at all — not `unknown`, not an empty literal. A default written
    into a store becomes an assertion that travels."""
    g = Graph(graph_id="plain")
    g.add_node(_unit())
    triples = _rdf(_export(g, tmp_path / "p.ttl"))
    for pred in ("createdBy", "lastEditedBy", "modifiedAt"):
        assert not list(triples.objects(None, rdflib.URIRef(EM_NS + pred)))
    assert not list(triples.objects(None, rdflib.URIRef(PROV_NS + "generatedAtTime")))


def test_e3_created_and_modified_come_back_told_apart(tmp_path):
    ttl = _export(_stamped_graph(), tmp_path / "a.ttl")
    importer = RDFImporter()
    rebuilt = importer.parse(ttl)
    assert len(rebuilt) == 1, importer.warnings
    # the two agents are the point: prov:wasAttributedTo alone could not say
    # WHICH hand it names, which is why the em: predicates exist
    assert read_stamps(rebuilt[0].find_node_by_id("US1")) == {
        "created_by": ORCID, "created_at": "2026-01-01T00:00:00Z",
        "modified_by": OTHER, "modified_at": "2026-02-02T00:00:00Z",
    }


def test_e4_the_round_trip_stays_isomorphic(tmp_path):
    ttl1 = _export(_stamped_graph(), tmp_path / "a.ttl")
    importer = RDFImporter()
    rebuilt = importer.parse(ttl1)
    ttl2 = _export(rebuilt[0], tmp_path / "b.ttl")
    assert isomorphic(to_isomorphic(_rdf(ttl1)), to_isomorphic(_rdf(ttl2)))


# ── E5 · the clock of an operation is to the millisecond (E.D., 12 Oct 2026) ──

def test_e5_the_op_clock_is_utc_to_the_millisecond():
    from s3dgraphy.editorial import now_op_iso
    stamp = now_op_iso()
    assert stamp.endswith("Z") and len(stamp) == len("2026-10-12T07:12:47.300Z")
    assert stamp[19] == "." and stamp[20:23].isdigit()


def test_e5_an_op_instant_keeps_its_milliseconds_and_a_second_keeps_its_spelling():
    from s3dgraphy.editorial import normalize_instant, normalize_op_instant
    # rdflib's spelling of an instant at the millisecond
    assert normalize_op_instant("2026-10-12T07:12:47.300000+00:00") == "2026-10-12T07:12:47.300Z"
    assert normalize_op_instant("2026-10-12T07:12:47.300Z") == "2026-10-12T07:12:47.300Z"
    assert normalize_op_instant("2026-10-12T07:12:47+00:00") == "2026-10-12T07:12:47Z"
    assert normalize_op_instant("2026-10-12T09:12:47.300+02:00") == "2026-10-12T09:12:47.300+02:00"
    # the editorial stamps stay at the second
    assert normalize_instant("2026-10-12T07:12:47.300Z") == "2026-10-12T07:12:47Z"


def test_e5_a_tombstone_comes_back_from_rdf_with_its_milliseconds(tmp_path):
    g = _stamped_graph()
    g.find_node_by_id("US1").data["removed"] = {"ts": "2026-10-12T07:12:49.900Z", "by": ORCID}
    rebuilt = RDFImporter().parse(_export(g, tmp_path / "t.ttl"))
    back = rebuilt[0].find_node_by_id("US1").data["removed"]
    assert back == {"ts": "2026-10-12T07:12:49.900Z", "by": ORCID}
