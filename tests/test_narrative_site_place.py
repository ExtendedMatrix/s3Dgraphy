"""«Dove si trova» is born from the SITE, not from the 3D scene.

The site is `GraphNode.data.site_position` (GEO1). The GeoPositionNode is the
ANCHOR of the 3D scene: its shift is an offset for the models, not where the dot
goes. The chapter used to be born from the shift, with the map on the geo node —
so a site placed only through `site_position` got no chapter, and a shifted
scene got a map of its origin.

Three cases, and the bake that has to draw the same point the chapter was born
from.
"""

from s3dgraphy import api as em
from s3dgraphy.graph import Graph
from s3dgraphy.narrative import build_narrative
from s3dgraphy.narrative.bake import bake_narrative
from s3dgraphy.nodes.geo_position_node import GeoPositionNode
from s3dgraphy.nodes.graph_node import GraphNode


def _graph(*, site=None, shift=None, graph_node=True) -> Graph:
    g = Graph(graph_id="pm")
    if graph_node:
        root = GraphNode("pm_graphroot", name="Porta Marina")
        root.data = {"site_position": site} if site else {}
        g.add_node(root)
    if shift:
        g.add_node(GeoPositionNode("GEO", shift_x=shift[0], shift_y=shift[1]))
    return g


def _where(narrative, lang="en"):
    title = "Where it is" if lang == "en" else "Dove si trova"
    return next((c for c in narrative.chapters if c.title == title), None)


SITE = {"lat": 40.7489, "lon": 14.4839, "crs": "EPSG:4326"}


def test_the_chapter_is_born_from_the_site_position_and_maps_the_graph():
    """Only a site position, no shift: before, no chapter at all."""
    n = build_narrative(_graph(site=SITE), "site_story")
    chapter = _where(n)
    assert chapter is not None and chapter.canonical
    maps = [b for b in chapter.blocks if b.view_type == "map"]
    assert [b.ref for b in maps] == ["pm_graphroot"]


def test_with_both_the_map_points_at_the_graph_not_at_the_scene_anchor():
    n = build_narrative(_graph(site=SITE, shift=(2400000.0, 4500000.0)),
                        "site_story")
    maps = [b.ref for b in _where(n).blocks if b.view_type == "map"]
    assert maps == ["pm_graphroot"], "the geo node is the 3D anchor, not the site"


def test_only_a_shift_gives_the_chapter_and_says_the_site_is_to_be_placed():
    """The scene says the graph IS somewhere; it does not say where the site is.
    So the chapter is born, the prose asks for the site, and no point is derived
    from the shift."""
    g = _graph(shift=(14.4823, 40.7497))
    n = build_narrative(g, "site_story", lang="it")
    chapter = _where(n, "it")
    assert chapter is not None
    prose = " ".join(b.text for b in chapter.blocks if b.block_type == "prose")
    assert prose.startswith("[da scrivere:") and "va posizionato" in prose
    maps = [b.ref for b in chapter.blocks if b.view_type == "map"]
    assert maps == ["pm_graphroot"]
    # …and the bake of that embed does not borrow the shift
    g.add_node(n)
    block = next(b for c in bake_narrative(g, n.node_id).chapters
                 for b in c.blocks if b.view_type == "map")
    assert "non registrata" in block.text
    assert "40.7497" not in block.text and not block.link


def test_only_a_shift_and_no_graph_node_gives_the_prose_alone():
    """Nothing honest to point a map at: the chapter says what is missing."""
    n = build_narrative(_graph(shift=(14.4823, 40.7497), graph_node=False),
                        "site_story")
    chapter = _where(n)
    assert chapter is not None
    assert not [b for b in chapter.blocks if b.block_type == "embed"]


def test_neither_gives_no_chapter():
    assert _where(build_narrative(_graph(), "site_story")) is None
    assert _where(build_narrative(_graph(graph_node=False), "site_story")) is None


def test_the_html_bake_prints_the_site_in_the_caption():
    g = _graph(site=SITE, shift=(2400000.0, 4500000.0))
    n = build_narrative(g, "site_story")
    g.add_node(n)
    html = em.export_narrative_html(g, n.node_id)
    assert "40.748900, 14.483900 (WGS84)" in html
    assert "mlat=40.748900&amp;mlon=14.483900" in html \
        or "mlat=40.748900&mlon=14.483900" in html
    assert "2400000" not in html


def test_an_old_embed_on_the_geo_node_keeps_the_shift():
    """Narratives saved before point the map at the geo node. They keep working:
    the shift, when there is one, is still what that block reads."""
    g = _graph(site=SITE, shift=(14.4823, 40.7497))
    from s3dgraphy.nodes.narrative_node import NarrativeNode
    n = NarrativeNode("N", "old")
    n.add_chapter("Dove si trova").add_embed("GEO", "map")
    g.add_node(n)
    block = next(b for c in bake_narrative(g, "N").chapters for b in c.blocks)
    assert "40.749700, 14.482300" in block.text


def test_an_old_embed_on_an_unshifted_geo_node_reads_the_graph_site():
    g = _graph(site=SITE, shift=(0.0, 0.0))
    from s3dgraphy.nodes.narrative_node import NarrativeNode
    n = NarrativeNode("N", "old")
    n.add_chapter("Dove si trova").add_embed("GEO", "map")
    g.add_node(n)
    block = next(b for c in bake_narrative(g, "N").chapters for b in c.blocks)
    assert "40.748900, 14.483900" in block.text, block.text
