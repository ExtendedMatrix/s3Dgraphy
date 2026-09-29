"""The stamp writes and reads its title and description (dtcstamp 46b3b78).

`emit` writes `self.label` / `self.description` from the resource's name and
description; `absorb` brings them to the node the stamp feeds, as a MARKED copy
and never over a person's words; the shelf keeps `dtcstamp.receipt()` — one
form, not two. A stamp without them stays valid.
"""

import pytest

from dtcstamp import receipt, substance, validate_stamp

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import DTCProcessNode, ResourceNode
from s3dgraphy.shelf import STAMP_RECEIPT_KEY, new_shelf, shelve_stamp
from s3dgraphy.stamp import absorb_stamp, clean_stamp, emit_stamp
from s3dgraphy.stamp.absorb import COPIED_FROM_STAMP

SHA_OUT = "sha256:" + "6e" * 32
SHA_IN = "sha256:" + "aa" * 32
TITLE = "Great Temple · modello per il web"
DESC = "Decimato a 50 000 facce dal rilievo 2015, per la pubblicazione."


def _graph(name=TITLE, description=DESC) -> Graph:
    g = Graph(graph_id="graph:gt")
    g.add_node(ResourceNode("res:nuvola", name="rilievo 2015", checksum=SHA_IN))
    g.add_node(ResourceNode("res:mesh", name=name, description=description,
                            checksum=SHA_OUT))
    g.add_node(DTCProcessNode("proc:dec", name="decimation",
                              dtc_kind="transformation"))
    g.add_edge("e1", "proc:dec", "res:nuvola", "dtc_had_input")
    g.add_edge("e2", "proc:dec", "res:mesh", "dtc_had_output")
    return g


def _desc(node):
    return (node.data or {}).get("description") or node.description


def test_emit_writes_title_and_description():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    validate_stamp(stamp)
    assert stamp["self"]["label"] == TITLE
    assert stamp["self"]["description"] == DESC
    # courtesy, not identity
    assert "label" not in str(substance(stamp).get("self", ""))


def test_a_name_that_repeats_the_id_is_not_a_title():
    stamp = clean_stamp(emit_stamp(_graph(name="res:mesh", description=""),
                                   "res:mesh"))
    assert "label" not in stamp["self"] and "description" not in stamp["self"]
    validate_stamp(stamp)                       # still a valid stamp


def test_the_full_round_emit_absorb_receipt():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))

    arrivo = Graph(graph_id="graph:arrivo")
    result = absorb_stamp(arrivo, stamp)
    assert result.applied
    assert sorted(result.courtesy) == ["description", "name"]
    node = arrivo.find_node_by_id("res:mesh")
    assert node.name == TITLE and _desc(node) == DESC
    assert sorted(node.data[COPIED_FROM_STAMP]) == ["description", "name"]
    # the stamp the arrival would emit says the same words
    again = clean_stamp(emit_stamp(arrivo, "res:mesh"))
    assert again["self"]["label"] == TITLE
    assert again["self"]["description"] == DESC
    assert substance(again) == substance(stamp)

    shelf = new_shelf()
    entry = shelve_stamp(shelf, stamp, locator="file:///gt/mesh.glb")
    assert entry["receipt"] == receipt(stamp)          # ONE form: dtcstamp's
    assert entry["receipt"]["title"] == TITLE
    assert entry["receipt"]["description"] == DESC
    assert entry["receipt"]["parents"] == [
        {"resource_id": "res:nuvola", "digest": SHA_IN}]
    assert entry["name"] == TITLE
    assert entry["checksum"] == SHA_OUT
    assert api.shelve_stamp(new_shelf(), stamp)["receipt"] == receipt(stamp)


def test_a_stamp_without_words_stays_valid_all_the_way():
    stamp = clean_stamp(emit_stamp(_graph(name="res:mesh", description=""),
                                   "res:mesh"))
    arrivo = Graph(graph_id="graph:arrivo")
    result = absorb_stamp(arrivo, stamp)
    assert result.applied and result.courtesy == []
    node = arrivo.find_node_by_id("res:mesh")
    assert node.name == "res:mesh" and not _desc(node)
    assert COPIED_FROM_STAMP not in node.data
    entry = shelve_stamp(new_shelf(), stamp)
    assert "title" not in entry["receipt"] and "description" not in entry["receipt"]
    assert entry["receipt"] == receipt(stamp)


def test_absorb_never_overwrites_what_a_person_wrote():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    host = Graph(graph_id="graph:host")
    host.add_node(ResourceNode("res:mesh", name="La mia mesh",
                               description="scritta da E.D.", checksum=SHA_OUT))
    result = absorb_stamp(host, stamp)            # brings a process: applied
    assert result.applied
    node = host.find_node_by_id("res:mesh")
    assert node.name == "La mia mesh"
    assert _desc(node) == "scritta da E.D."
    assert result.courtesy == []
    assert COPIED_FROM_STAMP not in node.data


def test_absorb_fills_only_the_blank_field():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    host = Graph(graph_id="graph:host")
    host.add_node(ResourceNode("res:mesh", name="La mia mesh", checksum=SHA_OUT))
    absorb_stamp(host, stamp)
    node = host.find_node_by_id("res:mesh")
    assert node.name == "La mia mesh"                 # the person's
    assert _desc(node) == DESC                        # the copy
    assert node.data[COPIED_FROM_STAMP] == ["description"]


def test_a_later_stamp_updates_a_copy_and_a_deduplicated_one_still_brings_words():
    first = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    host = Graph(graph_id="graph:host")
    absorb_stamp(host, first)
    later = clean_stamp(emit_stamp(_graph(name="Great Temple · web v2"),
                                   "res:mesh"))
    result = absorb_stamp(host, later)          # same substance: deduplicated
    assert result.deduplicated
    assert host.find_node_by_id("res:mesh").name == "Great Temple · web v2"
    assert "name" in result.courtesy


def test_dry_run_brings_no_words():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    host = Graph(graph_id="graph:host")
    absorb_stamp(host, clean_stamp(emit_stamp(_graph(name="res:mesh",
                                                     description=""), "res:mesh")))
    absorb_stamp(host, stamp, dry_run=True)
    assert host.find_node_by_id("res:mesh").name == "res:mesh"


def test_the_shelf_keeps_a_persons_name_and_dedups_by_content():
    stamp = clean_stamp(emit_stamp(_graph(), "res:mesh"))
    shelf = new_shelf()
    api.add_to_shelf(shelf, "file:///a.glb", resource_id="res:altro",
                     name="Il nome sullo scaffale", checksum=SHA_OUT)
    entry = shelve_stamp(shelf, stamp)
    assert entry["id"] and entry["name"] == "Il nome sullo scaffale"
    node = shelf.find_node_by_id("res:altro")
    assert node.data[STAMP_RECEIPT_KEY] == receipt(stamp)
    assert len([n for n in shelf.nodes if n.node_type == "resource"]) == 1
