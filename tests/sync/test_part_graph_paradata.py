"""Each saggio's graph carries only its own paradata, and the site graph
writes each ``has_first_epoch`` once (E.D., 12 Oct 2026, s3Dgraphy#36).

1. ``_part_graph`` keeps what the saggio's units reach — unit → property →
   extractor → document → author, and the members of a paradata group the
   unit reaches. A chain cited only by another saggio's units stays out,
   even though, cut from its unit, it still holds together (extractor ↔
   document ↔ author). What no unit of the site reaches stays in every
   graph, as before.
2. The pyarchinit importer and ``_enrich_into`` both wrote the
   ``has_first_epoch`` of a unit, with two ids. One writer is left: the
   importer's id, ``<unit>_has_first_epoch_<epoch>``.
"""
from __future__ import annotations

import re
from collections import Counter

from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.extractor_node import ExtractorNode
from s3dgraphy.nodes.group_node import ParadataNodeGroup
from s3dgraphy.nodes.property_node import PropertyNode
from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
from s3dgraphy.sync.graph_projector import GraphProjector

from tests.sync.test_saggio_under_the_site import _db

SAGGI = {"1": "S1", "2": "S2", "3": "S3", "4": "S4", "5": "S4"}


class _WithParadata(GraphProjector):
    """The site's graph plus: document D.01 (and its author) cited by US1
    and US2; document D.02 cited only by US4, through a property in a
    paradata group of US4; document D.03 tied only to an epoch."""

    def populate_graph(self, *args, **kwargs):
        g = super().populate_graph(*args, **kwargs)
        units = {re.sub(r"^.*?(\d+)$", r"\1", n.name): n.node_id
                 for n in g.nodes if isinstance(n, StratigraphicUnit)}
        g.add_node(DocumentNode("doc-D01", name="D.01"))
        g.add_node(AuthorNode("auth-ED", name="E.D."))
        g.add_edge("e-doc-auth", "doc-D01", "auth-ED", "has_author")
        for us in ("1", "2"):
            g.add_node(PropertyNode(f"p-{us}", name="description"))
            g.add_node(ExtractorNode(f"x-{us}", name=f"D.01.{us}"))
            g.add_edge(f"e1-{us}", units[us], f"p-{us}", "has_property")
            g.add_edge(f"e2-{us}", f"p-{us}", f"x-{us}", "has_data_provenance")
            g.add_edge(f"e3-{us}", f"x-{us}", "doc-D01", "extracted_from")
        g.add_node(ParadataNodeGroup("png-4", name="US4 paradata"))
        g.add_node(PropertyNode("p-4", name="material"))
        g.add_node(ExtractorNode("x-4", name="D.02.1"))
        g.add_node(DocumentNode("doc-D02", name="D.02"))
        g.add_edge("e-png", units["4"], "png-4", "has_paradata_nodegroup")
        g.add_edge("e-in-png", "p-4", "png-4", "is_in_paradata_nodegroup")
        g.add_edge("e2-4", "p-4", "x-4", "has_data_provenance")
        g.add_edge("e3-4", "x-4", "doc-D02", "extracted_from")
        epoch = next(n for n in g.nodes if type(n).__name__ == "EpochNode")
        g.add_node(DocumentNode("doc-D03", name="D.03"))
        g.add_edge("e-d03", "doc-D03", epoch.node_id, "has_first_epoch")
        return g


def _ids(graph):
    return {n.node_id for n in graph.nodes}


def test_a_saggio_s_graph_has_only_the_paradata_its_units_reach(tmp_path):
    db = _db(tmp_path, SAGGI)
    c = _WithParadata().populate_container(db, sito="TestSite",
                                           groups=["saggio"])
    s1, s2, s3, s4 = (c.graphs[f"TestSite|S{i}"] for i in range(1, 5))
    chain = {"doc-D01", "auth-ED"}
    # shared by S1 and S2: copied into both, and only there
    assert chain | {"p-1", "x-1"} <= _ids(s1)
    assert chain | {"p-2", "x-2"} <= _ids(s2)
    assert not (chain & (_ids(s3) | _ids(s4)))
    # another saggio's chain does not travel: US1's extractor is not in S2
    assert not ({"p-1", "x-1"} & _ids(s2))
    assert not ({"p-1", "x-1", "p-2", "x-2"} & _ids(s3))
    # through the paradata group: the property points INTO the group
    assert {"png-4", "p-4", "x-4", "doc-D02"} <= _ids(s4)
    for g in (s1, s2, s3):
        assert not ({"png-4", "p-4", "x-4", "doc-D02"} & _ids(g))
    # no unit of the site reaches D.03: it stays everywhere, as before
    for g in (s1, s2, s3, s4):
        assert "doc-D03" in _ids(g)
    # no edge left hanging
    for g in c.graphs.values():
        ids = _ids(g)
        assert all(e.edge_source in ids and e.edge_target in ids
                   for e in g.edges)


def test_the_site_graph_writes_each_first_epoch_once(tmp_path):
    db = _db(tmp_path, SAGGI)
    for groups in (None, ["saggio"]):
        g = GraphProjector().populate_graph(db, sito="TestSite", groups=groups)
        triples = Counter((e.edge_source, e.edge_type, e.edge_target)
                          for e in g.edges)
        assert max(triples.values()) == 1, [t for t, k in triples.items()
                                            if k > 1]
        first = [e for e in g.edges if e.edge_type == "has_first_epoch"]
        assert len(first) == 5
        # the importer's id, the form the readers already have
        assert all(e.edge_id.startswith(f"{e.edge_source}_has_first_epoch_")
                   for e in first)
        assert not any(e.edge_id.startswith("hfe_") for e in g.edges)
