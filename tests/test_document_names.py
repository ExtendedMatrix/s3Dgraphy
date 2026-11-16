"""MICRO-F-BUCKET-E-TILESET p.3 · one way of numbering the documents: the
highest + 1, a number used and then deleted never comes back (E.D. 16 Nov 2026)."""

from s3dgraphy.document_names import HIGH_WATER_KEY, next_document_name, remember_document_number
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit


def _g(*names):
    g = Graph("g")
    for i, n in enumerate(names):
        g.add_node(DocumentNode(f"d{i}", n))
    return g


def test_the_highest_plus_one_not_the_first_free():
    assert next_document_name(_g("D.01", "D.02", "D.13", "D.70")) == "D.71"
    assert next_document_name(_g("D.1", "D.3")) == "D.4"          # no zero: none
    assert next_document_name(_g("D.001")) == "D.002"              # three stay three
    assert next_document_name(_g("D.01", "D.1000")) == "D.1001"
    assert next_document_name(_g()) == "D.01"                      # a study's first
    assert next_document_name(_g("TM003", "Pianta")) == "D.01"     # outside the series
    assert next_document_name(_g("D.01"), after=["D.02"]) == "D.03"


def test_a_deleted_number_never_comes_back():
    g = _g("D.01", "D.02", "D.03")
    g.remove_node("d2")                                            # D.03, the highest
    assert g.data[HIGH_WATER_KEY] == 3
    assert next_document_name(g) == "D.04"
    g.remove_node("d0")                                            # a lower one: no change
    assert g.data[HIGH_WATER_KEY] == 3 and next_document_name(g) == "D.04"


def test_only_documents_and_only_the_series_are_remembered():
    g = _g("D.05")
    g.add_node(StratigraphicUnit("u", "D.09"))
    g.remove_node("u")
    assert HIGH_WATER_KEY not in g.data
    remember_document_number(g, "Catasto")
    assert HIGH_WATER_KEY not in g.data
    remember_document_number(g, "D.08")                            # renamed out of the series
    assert next_document_name(g) == "D.09"


def test_every_point_that_proposes_uses_the_one_rule(tmp_path):
    from s3dgraphy import door
    from s3dgraphy.gis.document import next_document_name as gis_next
    assert gis_next is next_document_name
    g = _g("D.01", "D.70")
    g.remove_node("d1")                                            # D.70 deleted
    pic = tmp_path / "pianta.png"
    pic.write_bytes(b"\x89PNG\r\n\x1a\n")
    r = door.bring_in(g, [{"path": str(pic)}], title="Pianta", date="1835")
    assert g.find_node_by_id(r["document_id"]).name == "D.71"
