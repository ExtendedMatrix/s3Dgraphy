"""Se3 + Se4 — importer edge hygiene and paradata propagation hygiene.

Se3: the GraphML line style is a weak signal. A dashed connector defaults to
`has_data_provenance` and a solid one to `is_after`; when the endpoints say
otherwise, the endpoints win — but only where the datamodel leaves exactly one
reading. Where several relations (or none) fit, nothing is invented and the edge
is left to degrade with a warning: that is a real authorial anomaly, and the
report isolates it.

Se4: `connect_paradatagroup_propertynode_to_stratigraphic` materialises
`US → property` edges out of `US → group → property`. Those edges are DERIVED and
are now marked as such; and the `generic_connection` fallback it used to rely on
is legacy-only, since Se1 made the canonical link survive.
"""

import pytest

from s3dgraphy.graph import Graph
from s3dgraphy.importer.import_graphml import GraphMLImporter
from s3dgraphy.nodes.combiner_node import CombinerNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import ParadataNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import (SpecialFindUnit,
                                                StratigraphicUnit,
                                                VirtualStratigraphicUnit)


@pytest.fixture
def importer():
    return GraphMLImporter(filepath="<none>", graph=Graph(graph_id="g"))


def _prop(node_id="P1"):
    return PropertyNode(node_id=node_id, name="height",
                        property_type="dimension", value="3")


# ── Se3: the stratigraphic type list comes from the datamodel ─────────────────
def test_stratigraphic_types_are_datamodel_driven():
    from s3dgraphy.classification import ALL_US_TYPES
    types = GraphMLImporter._stratigraphic_types()
    assert set(ALL_US_TYPES) <= types
    # the four the hand-kept list used to miss
    assert {"RSF", "USN", "serUSD", "UL"} <= types
    # the legacy node_type VirtualStratigraphicUnit registers itself under
    assert "StratigraphicNode" in types
    # an UnknownNode is not a stratigraphic unit
    assert "unknown" not in types


def test_the_legacy_stratigraphic_node_type_reaches_has_property(importer):
    """37 edges in the corpus: source node_type `StratigraphicNode` (a USV) → a
    PropertyNode. The old hand-kept list did not contain that name, so the dashed
    connector kept its `has_data_provenance` default and was refused."""
    got = importer.enhance_edge_type(
        "has_data_provenance", VirtualStratigraphicUnit("V1", "usv"), _prop())
    assert got == "has_property"


def test_property_to_document_is_documentation(importer):
    """BUGFIX-CONN3: a PropertyNode pointing at a Document reads as
    `has_documentation` (P70i — the property is documented in this source). It is
    NO LONGER `has_visual_reference`: CONN2 moved that to PropertyNode→ResourceNode
    (an image resource), so a legacy dashed property→document connector is
    documentation, not a visual reference. has_documentation.source was widened
    to include PropertyNode (v1.6.7) for exactly this reading."""
    assert importer.enhance_edge_type(
        "has_data_provenance", _prop(), DocumentNode("D1", "D.1")
    ) == "has_documentation"
    # the extraction case still wins for an Extractor source
    assert importer.enhance_edge_type(
        "has_data_provenance", ExtractorNode("EX1", "m"), DocumentNode("D1", "D.1")
    ) == "extracted_from"


def test_document_to_its_property_is_has_property(importer):
    """G2 · a dashed connector from a (master) document to its own property —
    its dating, `absolute_time_start` — is the document's property: the reading
    `_enrich_canonical_documents` already gives it. Measured on Templu Mare
    (4 Oct 2026): five came out generic_connection and reached the room so."""
    dating = PropertyNode(node_id="P9", name="absolute_time_start",
                          property_type="absolute_time_start", value="170")
    got = importer.enhance_edge_type(
        "has_data_provenance", DocumentNode("D10", "D.10"), dating)
    assert got == "has_property"
    from s3dgraphy.edges.connection_resolver import connection_allowed
    assert connection_allowed(DocumentNode("D10", "D.10"), dating, got)


def test_combiner_to_document_is_left_generic_with_a_warning(importer):
    """BUGFIX-CONN3: a CombinerNode/bare ParadataNode → Document has no honest
    single relation (a combiner aggregates extractors; it cites no document, and
    the DTC chain is not synthesised at import). It is left as `generic_connection`
    with a warning rather than asserting a relation — and never the now-illegal
    `has_visual_reference`."""
    got = importer.enhance_edge_type(
        "has_data_provenance", CombinerNode("C1", "C.01"), DocumentNode("D1", "D.1")
    )
    assert got == "generic_connection"
    assert any("generic_connection" in w for w in importer.graph.warnings)


# ── Se3: a mis-endpointed `is_after` is re-read from its endpoints ────────────
@pytest.mark.parametrize("source,expected", [
    (StratigraphicUnit("US1", "u"), "has_property"),
    (SpecialFindUnit("SF1", "find"), "has_property"),
])
def test_is_after_towards_a_property_becomes_has_property(importer, source, expected):
    assert importer.enhance_edge_type("is_after", source, _prop()) == expected


def test_is_after_from_a_property_becomes_data_provenance(importer):
    assert importer.enhance_edge_type(
        "is_after", _prop(), ExtractorNode("EX1", "m")) == "has_data_provenance"


def test_a_valid_stratigraphic_is_after_is_never_touched(importer):
    got = importer.enhance_edge_type("is_after", StratigraphicUnit("US1", "a"),
                                     StratigraphicUnit("US2", "b"))
    assert got == "is_after"


def test_nothing_is_invented_when_no_relation_fits(importer):
    """`combiner → SF` (7 in the corpus) admits no relation at all: the edge keeps
    its declared type and `add_edge` degrades it, which is the honest outcome."""
    got = importer.enhance_edge_type("is_after", CombinerNode("C1", "c"),
                                     SpecialFindUnit("SF1", "find"))
    assert got == "is_after"
    from s3dgraphy.edges.connection_resolver import candidate_edge_types
    assert candidate_edge_types(CombinerNode("C1", "c"),
                                SpecialFindUnit("SF1", "f")) == []


def test_nothing_is_invented_when_several_relations_fit(importer):
    """A dashed connector between two units could be any stratigraphic relation —
    the endpoints cannot decide, so it is left alone."""
    got = importer.enhance_edge_type("has_data_provenance",
                                     VirtualStratigraphicUnit("V1", "a"),
                                     SpecialFindUnit("SF1", "b"))
    assert got == "has_data_provenance"


# ── Se4: paradata propagation hygiene ─────────────────────────────────────────
def _paradata_graph(canonical=True):
    """A US whose paradata group holds one property. `canonical=False` mimics a
    graph imported before Se1, where the US→group link was degraded."""
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "wall"))
    g.add_node(ParadataNodeGroup("PD1", "US1_PD"))
    g.add_node(_prop())
    g.add_edge("p_in", "P1", "PD1", "is_in_paradata_nodegroup")
    g.add_edge("us_pd", "US1", "PD1",
               "has_paradata_nodegroup" if canonical else "generic_connection")
    return g


def test_derived_property_edges_are_marked_with_their_group():
    g = _paradata_graph()
    stats = g.connect_paradatagroup_propertynode_to_stratigraphic(verbose=False)
    assert stats["connections_created"] == 1
    edge = next(e for e in g.edges if e.edge_type == "has_property")
    assert edge.attributes["derived"] is True
    assert edge.attributes["derived_from"] == "PD1"   # which group justified it


def test_an_authored_property_edge_stays_unmarked():
    g = _paradata_graph()
    g.add_edge("authored", "US1", "P1", "has_property")
    g.connect_paradatagroup_propertynode_to_stratigraphic(verbose=False)
    edge = g.find_edge_by_id("authored")
    assert "derived" not in edge.attributes


def test_the_canonical_link_needs_no_guessing():
    """Se1 made `US ─has_paradata_nodegroup→ group` survive, so the legacy branch
    must not fire on a healthy graph."""
    g = _paradata_graph(canonical=True)
    assert g.find_edge_by_id("us_pd").edge_type == "has_paradata_nodegroup"
    stats = g.connect_paradatagroup_propertynode_to_stratigraphic(verbose=False)
    assert stats["legacy_generic_guesses"] == 0
    assert stats["connections_created"] == 1


def test_the_legacy_branch_still_rescues_a_degraded_graph_and_says_so():
    g = _paradata_graph(canonical=False)
    stats = g.connect_paradatagroup_propertynode_to_stratigraphic(verbose=False)
    assert stats["connections_created"] == 1
    assert stats["legacy_generic_guesses"] == 1   # visible: it had to guess


def test_has_property_no_longer_survives_by_accident():
    """It used to validate only because `DocumentNode` was unresolvable and made
    the whole check permissive. Both admitted sources now resolve properly, and a
    source the datamodel does not admit is refused."""
    assert Graph.validate_connection("US", "property", "has_property") is True
    assert Graph.validate_connection("document", "property", "has_property") is True
    assert Graph.validate_connection("extractor", "property", "has_property") is False


# ── Se2b + Se-Nodi: what the importer cannot type becomes a warning ───────────
def _graphml(body):
    """Minimal yEd GraphML around `body` (the <node>/<edge> elements)."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
         xmlns:y="http://www.yworks.com/xml/graphml">
  <key for="node" id="d6" yfiles.type="nodegraphics"/>
  <key for="edge" id="d10" yfiles.type="edgegraphics"/>
  <graph edgedefault="directed">{body}</graph>
</graphml>"""


def _roleless_group(node_id="n0", label="walls"):
    """A yEd group with the DEFAULT colours — i.e. no EM palette role."""
    return f"""
    <node id="{node_id}" yfiles.foldertype="group"><data key="d6">
      <y:ProxyAutoBoundsNode><y:Realizers active="0"><y:GroupNode>
        <y:Geometry height="80" width="140" x="0" y="0"/>
        <y:Fill color="#F5F5F5" transparent="false"/>
        <y:NodeLabel backgroundColor="#EBEBEB">{label}</y:NodeLabel>
      </y:GroupNode></y:Realizers></y:ProxyAutoBoundsNode>
    </data><graph edgedefault="directed"/></node>"""


def _import(body):
    from s3dgraphy import api
    graph, _w = api.graphml_to_graph(_graphml(body))
    return graph


def test_a_roleless_group_is_reported_to_the_author():
    g = _import(_roleless_group(label="PODIUM"))
    assert any("PODIUM" in w and "no EM role" in w for w in g.warnings)


def test_a_roleless_group_gets_no_epoch_edge():
    """The 131 `Group → EpochNode` of the corpus: the datamodel refuses them, the
    members already carry their own epoch, so the importer stops emitting them."""
    from s3dgraphy.graph import Graph
    assert Graph.validate_connection("Group", "EpochNode", "has_first_epoch") is False
    g = _import(_roleless_group())
    assert not [e for e in g.edges if e.edge_type == "has_first_epoch"]


def test_membership_into_a_roleless_group_is_not_an_edge_anomaly():
    """Those edges say WHICH elements sit in the box — worth keeping — but they
    are organisational, not a relation error: the report counts them apart."""
    from s3dgraphy import api
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.group_node import GroupNode
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "wall"))
    g.add_node(GroupNode("G1", "walls"))
    g.add_edge("m", "US1", "G1", "generic_connection")
    rep = api.connection_report(g)
    assert rep["author_warning"] == 1
    assert rep["already_generic"] == 0 and rep["would_degrade"] == 0


def test_an_untyped_node_is_reported_to_the_author():
    """A yEd shape matching no EM type. Its label often reveals the intent
    (`SF04.2`, `D38.1`) but reading a type out of a label would be guessing."""
    body = """
    <node id="n1"><data key="d6"><y:ShapeNode>
      <y:Geometry height="30" width="30" x="0" y="0"/>
      <y:Fill color="#FFFFFF"/>
      <y:BorderStyle color="#000000" type="line" width="1.0"/>
      <y:NodeLabel>SF04.2</y:NodeLabel>
      <y:Shape type="star5"/>
    </y:ShapeNode></data></node>"""
    g = _import(body)
    bare = [n for n in g.nodes if n.node_type == "Node"]
    assert bare, "expected an untyped node"
    assert any("no recognised EM type" in w for w in g.warnings)


def test_edges_touching_an_untyped_node_are_the_nodes_problem():
    from s3dgraphy import api
    from s3dgraphy.graph import Graph
    from s3dgraphy.nodes.base_node import Node
    g = Graph(graph_id="g")
    g.add_node(StratigraphicUnit("US1", "wall"))
    g.add_node(Node("N1", "SF04.2"))
    g.edges.append(__import__("s3dgraphy.edges.edge", fromlist=["Edge"]).Edge(
        "e", "N1", "US1", "is_after"))
    g._indices_dirty = True
    rep = api.connection_report(g)
    assert rep["author_warning"] == 1
    assert rep["would_degrade"] == 0   # not an edge error: the endpoint has no type


# IMPKEYS (2026-08-08): removed test_the_graph_node_is_typed_and_owns_its_author.
# It drove the now-deleted dead method process_general_data; IMP1's
# materialize_graph_scope is the real wiring (graph-self GraphNode + graph-scope
# author as a PDG member via is_in_paradata_nodegroup, not has_author from the
# graph node). The old has_author-from-graph model is superseded, not pending.
