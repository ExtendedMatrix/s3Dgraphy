"""Shelf, Traccia A: what a resource is FOR, the asset nobody downloads, and the
table that shows both.

Four additions, and each one exists because of a specific way the shelf could
lie:

* **role** (`comparandum` / `internal_source`) is ORTHOGONAL to the fences. The
  tempting shortcut — "external scope means comparandum" — is wrong in both
  directions: I hold up a model of *my own* study next to this one, and I cite a
  colleague's URI as evidence inside my own argument. So the role is stated, and
  the matrix below has cells in every corner;
* **URI-only acquisition**: pasting a link must not copy bytes anywhere, and
  pasting it twice must not grow the shelf. The idempotence is the URI's, the way
  the fs record's is the absolute path's;
* **in_use** is DERIVED. A stored flag would be wrong the first time somebody
  deleted the RM that used a photograph, so it is the hatting reference-check —
  and it must be the SAME check the remove-cleanup trusts, not a second one;
* **the table** is a read-model: change the shelf and the rows change.
"""

import json
import os
import tempfile

from s3dgraphy import api
from s3dgraphy.nodes.resource_node import ResourceNode

URI = "https://zenodo.org/records/12345/files/tempio.glb"


def a_shelf_with_three():
    """One shelf, three residences, three roles — the matrix the measures need."""
    shelf = api.new_shelf()
    mine = api.add_to_shelf(
        shelf, "s3://em-assets/aabbcc", name="tempio (mio)",
        checksum="sha256:aabbcc", scope="own-study", residency="resident",
        # MY OWN asset, held up as a comparandum. The cell the "derive it from
        # the scope" shortcut gets wrong.
        role="comparandum", media_type="model/gltf-binary", size=104857,
        origin={"repo": "s3", "capabilities": []})
    theirs = api.add_to_shelf(
        shelf, URI, name="tempio (altrove)", scope="other-HDT",
        # somebody else's URI, used as a source INSIDE this study's reasoning
        role="internal_source", media_type="model/gltf-binary",
        access={"mode": "subscribe"})
    unset = api.add_to_shelf(
        shelf, "/scavi/2026/foto/us12.jpg", name="us12.jpg",
        scope="own-study", residency="resident", media_type="image/jpeg",
        size=2048)
    return shelf, mine, theirs, unset


# ── A1 · the role, and its orthogonality ────────────────────────────────────

def test_the_two_roles_come_from_the_class_that_validates_them():
    assert api.resource_roles() == ("comparandum", "internal_source")
    assert ResourceNode.ROLES == api.resource_roles()


def test_a_third_role_is_refused_rather_than_kept():
    """A role outside the two is not a role: keeping it would put a word in the
    filters that nothing can ever match. Two values, and a third case gets
    declared instead of slipped in."""
    node = ResourceNode("r1")
    for bad in ("nemico", "COMPARANDUM", "", "source"):
        try:
            node.set_role(bad)
        except ValueError as exc:
            assert "comparandum" in str(exc)
        else:                                        # pragma: no cover
            raise AssertionError(f"{bad!r} was accepted as a role")


def test_an_unstated_role_stays_unstated():
    """No `effective_role`, deliberately: neither value is what a resource is by
    default, so answering one would invent the claim."""
    node = ResourceNode("r1")
    assert node.role() is None
    assert "role" not in node.data
    assert not hasattr(node, "effective_role")


def test_the_role_is_independent_of_the_fence_and_of_where_the_bytes_are():
    """The matrix, with the corners populated: own-study×comparandum,
    other-HDT×internal_source, own-study×unset."""
    _shelf, mine, theirs, unset = a_shelf_with_three()
    matrix = {(e["effective_scope"], e["effective_residency"], e["role"])
              for e in (mine, theirs, unset)}
    assert ("own-study", "resident", "comparandum") in matrix
    assert ("other-HDT", "reference", "internal_source") in matrix
    assert ("own-study", "resident", None) in matrix


def test_the_role_survives_save_load_and_the_emjson():
    shelf, mine, theirs, _unset = a_shelf_with_three()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "shelf.em.json")
        api.save_shelf(shelf, path)
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        # in the FILE, not only in the object: this is what another tool reads
        text = json.dumps(doc)
        assert '"role": "comparandum"' in text
        assert '"role": "internal_source"' in text
        back, _warnings = api.load_shelf(path)
    roles = {e["name"]: e["role"] for e in api.list_shelf(back)}
    assert roles[mine["name"]] == "comparandum"
    assert roles[theirs["name"]] == "internal_source"
    assert roles["us12.jpg"] is None


def test_a_re_drag_of_the_same_bytes_states_the_role_on_the_curated_entry():
    """Dedup is by content, so the second add lands on the existing entry — and
    it must still be able to SAY what the resource is for. Dropping the role here
    would make the same call behave differently depending on history."""
    shelf = api.new_shelf()
    first = api.add_to_shelf(shelf, "/a/tempio.glb", name="tempio",
                             checksum="sha256:aabbcc")
    assert first["role"] is None
    again = api.add_to_shelf(shelf, "/altro/tempio.glb", name="tempio (copia)",
                             checksum="sha256:aabbcc", role="comparandum")
    assert again["id"] == first["id"], "the same bytes are the same resource"
    assert again["role"] == "comparandum"
    assert len(api.list_shelf(shelf)) == 1


def test_hatting_carries_the_role_into_the_study_graph():
    """The role belongs to the resource, and the study graph references the SAME
    resource — so the two must not disagree about what it is for."""
    from s3dgraphy.graph import Graph

    shelf, mine, _theirs, _unset = a_shelf_with_three()
    study = Graph(graph_id="scavo")
    node = api.instantiate_from_shelf(shelf, mine["id"], study)
    assert node.data.get("role") == "comparandum"
    assert node.data.get("checksum") == "sha256:aabbcc"


# ── A2 · the asset nobody downloads ─────────────────────────────────────────

def test_the_uri_mapping_ships_and_records_the_access_protocol():
    from s3dgraphy.acquisition import available_mappings

    # it ships as a FILE beside fs.json and ercolano.json: a new source is a
    # mapping, not code (the xlsx-import seam)
    assert "uri" in available_mappings()
    record = api.uri_acquisition_record(URI, access={"mode": "subscribe",
                                                     "endpoint": "https://zenodo.org/login"})
    assert record["record_id"] == URI, "the URI is its own record id"
    assert record["protocol"] == "https"
    assert record["access"] == {"mode": "subscribe",
                                "endpoint": "https://zenodo.org/login"}
    assert record["media_type"] == "model/gltf-binary"
    descriptor = api.apply_acquisition_mapping("uri", record)
    assert descriptor["asset"]["ref"] == URI
    assert descriptor["asset"]["access"]["mode"] == "subscribe"
    # …and the METHOD says what happened: nothing was fetched
    assert descriptor["acquisition"]["method"] == "uri_reference"


def test_the_two_access_modes_and_nothing_else():
    assert api.access_modes() == ("open", "subscribe")
    try:
        api.uri_acquisition_record(URI, access={"mode": "maybe"})
    except ValueError as exc:
        assert "open" in str(exc) and "subscribe" in str(exc)
    else:                                            # pragma: no cover
        raise AssertionError("an unknown access mode was accepted")


def test_an_open_link_defaults_to_open_and_a_record_page_is_named_by_its_host():
    plain = api.uri_acquisition_record("https://iiif.example.org/img/foto.jpg")
    assert plain["access"]["mode"] == "open"
    assert plain["name"] == "foto.jpg"
    page = api.uri_acquisition_record("https://zenodo.org/records/12345")
    # "12345" is not what anybody is looking for in a list
    assert page["name"] == "zenodo.org"


def test_a_uri_becomes_a_shelf_entry_with_no_bytes_anywhere():
    record = api.uri_acquisition_record(URI, access="subscribe")
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record))
    entry = info["entry"]
    assert entry["locator"] == URI
    assert entry["kind"] == "http_url"
    # NO bytes: nothing was hashed, because there is nothing here to hash
    assert "checksum" not in entry
    assert entry["effective_residency"] == "reference"
    assert entry["access"]["mode"] == "subscribe"
    assert entry["origin"]["repo"] == "zenodo.org"
    assert entry["origin"]["protocol"] == "https"


def test_a_uri_acquisition_never_fetches_anything(monkeypatch):
    """THE claim of this whole path, measured rather than asserted in prose: no
    request goes out and no object store is touched. Both doors are nailed shut
    for the duration — urllib and the S3 client (boto3) — and the acquisition still
    completes, which is only possible if it never wanted them."""
    import urllib.request

    def refuse(*_a, **_k):                           # pragma: no cover — must not run
        raise AssertionError("the URI path tried to FETCH something")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(urllib.request, "urlretrieve", refuse, raising=False)

    import builtins

    real_import = builtins.__import__

    def no_object_store(name, *args, **kwargs):
        if name.split(".")[0] in ("boto3", "botocore"):   # pragma: no cover
            raise AssertionError("the URI path reached for an object store")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_object_store)

    record = api.uri_acquisition_record(URI, access="subscribe")
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record))
    monkeypatch.undo()
    # …and the proof in the data: nothing was hashed, because there is nothing
    # here to hash. The identity of this entry IS the URI.
    assert "checksum" not in info["entry"]
    assert info["entry"]["locator"] == URI
    assert api.shelf_table(shelf)[0]["RESIDENCE"] == "uri"


def test_the_uri_acquisition_records_a_d12_event():
    record = api.uri_acquisition_record(URI, access="open")
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record))
    event = shelf.find_node_by_id(info["acquisition_id"])
    assert event is not None
    assert event.node_type == "dtc_acquisition"
    assert event.data.get("method") == "uri_reference"
    assert event.data.get("record_url") == URI
    # …wired to what it produced (prov:generated / crmdig:L11)
    assert any(e.edge_source == info["acquisition_id"]
               and e.edge_target == info["resource_id"]
               and e.edge_type == "dtc_had_output" for e in shelf.edges)


def test_uri_reference_is_a_declared_acquisition_kind():
    """It is in the datamodel vocabulary, not a literal invented at the call
    site — so the event carries a validated `dtc_kind` and a picker can show it.
    (`download` would have been a lie: nothing was retrieved.)"""
    from s3dgraphy.utils.utils import get_dtc_kinds

    assert "uri_reference" in get_dtc_kinds()["acquisition"]
    record = api.uri_acquisition_record(URI)
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record))
    event = shelf.find_node_by_id(info["acquisition_id"])
    assert event.data.get("dtc_kind") == "uri_reference"


def test_pasting_the_same_uri_twice_is_one_entry():
    """Idempotent on the URI, the way the fs record is on the absolute path."""
    record = api.uri_acquisition_record(URI, access="subscribe")
    descriptor = api.apply_acquisition_mapping("uri", record)
    first, shelf = api.acquire_from_descriptor(descriptor)
    before = len(api.list_shelf(shelf))
    second, shelf = api.acquire_from_descriptor(descriptor, shelf)
    assert second["resource_id"] == first["resource_id"]
    assert second["acquisition_id"] == first["acquisition_id"]
    assert len(api.list_shelf(shelf)) == before == 1


def test_an_empty_uri_is_refused():
    for bad in ("", "   ", None):
        try:
            api.uri_acquisition_record(bad)
        except ValueError:
            pass
        else:                                        # pragma: no cover
            raise AssertionError(f"{bad!r} was accepted as a URI")


# ── A3 · only on the shelf, or in use? ──────────────────────────────────────

def test_a_hatted_resource_is_in_use_and_an_unhatted_one_is_not():
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes import EpochNode

    shelf, mine, _theirs, unset = a_shelf_with_three()
    study = Graph(graph_id="scavo")
    study.add_node(EpochNode(node_id="ep1", name="Fase 1", start_time=-100,
                             end_time=0))
    container = api.container_of(study, shelf=shelf)

    only = api.shelf_entry_status(container, mine["id"])
    assert only["in_use"] is False
    assert only["mode"] == "only_shelf"
    assert only["role"] == "comparandum", "the role is reported either way"

    api.hat_as_representation_model(study, mine["id"], shelf=shelf,
                                    epochs=["ep1"])
    used = api.shelf_entry_status(container, mine["id"])
    assert used["in_use"] is True
    assert used["mode"] == "used_in_graph"
    assert used["used_by"] and used["used_by"][0]["node_type"] == \
        "representation_model"
    assert used["used_by"][0]["graph_id"] == "scavo"

    # the other one never left the shelf
    assert api.shelf_entry_status(container, unset["id"])["in_use"] is False


def test_taking_the_hat_off_makes_it_unused_again():
    """The reason this is derived: a stored flag would still say «in use»."""
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes import EpochNode

    shelf, mine, _t, _u = a_shelf_with_three()
    study = Graph(graph_id="scavo")
    study.add_node(EpochNode(node_id="ep1", name="Fase 1", start_time=-100,
                             end_time=0))
    container = api.container_of(study, shelf=shelf)
    hatted = api.hat_as_representation_model(study, mine["id"], shelf=shelf,
                                            epochs=["ep1"])
    assert api.shelf_entry_status(container, mine["id"])["in_use"] is True
    study.remove_node(hatted["rm_id"])
    assert api.shelf_entry_status(container, mine["id"])["in_use"] is False
    assert api.shelf_entry_status(container, mine["id"])["mode"] == "only_shelf"


def test_the_acquisition_event_is_not_a_use():
    """Every acquired resource has a D12 pointing at it. If that counted, every
    entry would read «in use» the moment it arrived."""
    record = api.uri_acquisition_record(URI)
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record))
    status = api.shelf_entry_status(shelf, info["resource_id"])
    assert status["in_use"] is False
    assert status["used_by"] == []


def test_in_use_is_the_same_check_the_remove_cleanup_trusts():
    """One reference-check, two callers: «is this in use?» must not have two
    answers depending on who asks."""
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes import EpochNode

    shelf = api.new_shelf()
    shelf.add_node(EpochNode(node_id="ep1", name="Fase 1", start_time=-100,
                             end_time=0))
    entry = api.add_to_shelf(shelf, "/a/b.glb", name="b.glb")
    api.hat_as_representation_model(shelf, entry["id"], shelf=shelf,
                                    epochs=["ep1"])
    status = api.shelf_entry_status(shelf, entry["id"])
    removal = api.remove_shelf_resource(shelf, entry["id"])
    assert status["in_use"] is removal["referenced"] is True
    assert removal["removed"] is False, "a resource in use is not removed"


# ── A4 · the EM Data table ──────────────────────────────────────────────────

def test_the_table_columns_are_declared_in_one_place():
    columns = api.shelf_table_columns()
    for expected in ("NAME", "MEDIA_TYPE", "RESIDENCE", "LOCATOR", "ROLE",
                     "MODE", "SIZE", "SCOPE"):
        assert expected in columns
    from s3dgraphy.shelf import SHELF_COLUMNS
    assert columns == tuple(SHELF_COLUMNS)


def test_the_shelf_sheet_is_not_forced_into_em_data_xlsx():
    """`_SHEETS` is what the xlsx importer REQUIRES and it fails fast on a
    missing sheet — adding `Shelf` there would invalidate every workbook that
    exists. The shelf's round-trip is the em.json."""
    assert "Shelf" not in api.em_data_sheets()
    assert "Shelf" not in api.em_data_columns()


def test_every_row_has_every_column_for_a_mixed_shelf():
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes import EpochNode

    shelf, mine, theirs, unset = a_shelf_with_three()
    # the URI-only entry, acquired the way a paste does it
    record = api.uri_acquisition_record("https://iiif.example.org/img/foto.jpg",
                                        access="open")
    info, shelf = api.acquire_from_descriptor(
        api.apply_acquisition_mapping("uri", record), shelf)
    study = Graph(graph_id="scavo")
    study.add_node(EpochNode(node_id="ep1", name="Fase 1", start_time=-100,
                             end_time=0))
    api.hat_as_representation_model(study, mine["id"], shelf=shelf,
                                    epochs=["ep1"])
    container = api.container_of(study, shelf=shelf)

    rows = {r["NAME"]: r for r in api.shelf_table(container)}
    assert set(rows) == {"tempio (mio)", "tempio (altrove)", "us12.jpg",
                         "foto.jpg"}
    for row in rows.values():
        assert set(row) == set(api.shelf_table_columns())

    # …and the cells say what they should. THREE residences, three roles, both
    # modes — the matrix in one table.
    assert rows["tempio (mio)"]["RESIDENCE"] == "s3"
    assert rows["tempio (mio)"]["ROLE"] == "comparandum"
    assert rows["tempio (mio)"]["MODE"] == "used_in_graph"
    assert rows["tempio (mio)"]["SIZE"] == 104857
    assert rows["tempio (mio)"]["SCOPE"] == "own-study"

    assert rows["tempio (altrove)"]["RESIDENCE"] == "uri"
    assert rows["tempio (altrove)"]["ROLE"] == "internal_source"
    assert rows["tempio (altrove)"]["MODE"] == "only_shelf"
    assert rows["tempio (altrove)"]["ACCESS"] == "subscribe"

    assert rows["us12.jpg"]["RESIDENCE"] == "disk"
    assert rows["us12.jpg"]["ROLE"] == "", "unstated reads empty, not a guess"
    assert rows["us12.jpg"]["MEDIA_TYPE"] == "image/jpeg"

    assert rows["foto.jpg"]["RESIDENCE"] == "uri"
    assert rows["foto.jpg"]["ACCESS"] == "open"
    assert rows["foto.jpg"]["CHECKSUM"] == "", "a URI has no bytes to hash"


def test_the_table_is_derived_and_follows_the_shelf():
    """A read-model: it is not a second place where a shelf lives."""
    shelf, mine, _t, _u = a_shelf_with_three()
    before = api.shelf_table(shelf)
    assert len(before) == 3
    api.add_to_shelf(shelf, "https://altro.org/z.jpg", name="z.jpg",
                     role="comparandum")
    after = api.shelf_table(shelf)
    assert len(after) == 4
    api.remove_from_shelf(shelf, mine["id"])
    assert len(api.shelf_table(shelf)) == 3
    # …and a role stated afterwards shows up without anybody rebuilding anything
    api.add_to_shelf(shelf, "", resource_id=_u["id"], role="internal_source")
    roles = {r["NAME"]: r["ROLE"] for r in api.shelf_table(shelf)}
    assert roles["us12.jpg"] == "internal_source"


def test_a_document_without_a_shelf_tables_to_nothing():
    from s3dgraphy.graph import Graph

    assert api.shelf_table(Graph(graph_id="scavo")) == []
    assert api.shelf_table(api.container_of(Graph(graph_id="scavo"))) == []
