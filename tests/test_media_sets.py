"""MICRO-B-DOCUMENTI-MEDIA (14 Nov 2026) — one node per set, not per photograph.

* implicit members: the list inside the set (``data.members``), a node only
  when used (``materialize_member``);
* logical groups (``file_set`` drawing from a directory) with a role of the
  vocabulary ``em-media-role``, extensible by the project;
* sets inside sets (``has_sub_resource``, connections 1.6.55): the datamodel,
  the RDF projection, the em.json round trip;
* the catalogue: one document, open or closed, entries cited «D.30 · 18383»,
  inheriting the catalogue's dates and authors (resolver level ``set``);
* Metashape's importer: the folder with its rows, the photographs implicit.
"""

import json
import os
import pathlib

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.author_node import AuthorNode
from s3dgraphy.nodes.document_node import DocumentNode
from s3dgraphy.nodes.graph_node import GraphNode
from s3dgraphy.resolvers import get_rule, resolve_provenance
from s3dgraphy.resources import catalog as CAT
from s3dgraphy.resources import files as F
from s3dgraphy.resources import media_roles as MR
from s3dgraphy.resources import sets as S

dtcstamp = pytest.importorskip("dtcstamp")

TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "stratigraph-templates"


def _photos(root: pathlib.Path, cats=3, pieces=2, per=3) -> pathlib.Path:
    """A lapidary on the disk: <cat>/<inventory>/<photo>.jpg, small bytes."""
    lap = root / "lapidario"
    for c in range(cats):
        for p in range(pieces):
            d = lap / f"Cat{c}" / f"{18380 + c * 10 + p}"
            d.mkdir(parents=True, exist_ok=True)
            for i in range(per):
                (d / f"IMG_{i:03d}.jpg").write_bytes(b"\xff\xd8" + f"{c}-{p}-{i}".encode())
    return lap


def _graph():
    g = Graph("g")
    g.add_node(GraphNode("graph-g", name="g"))
    return g


def _directory(g, folder, rid="res:lap", name="Lapidario"):
    rows = F.directory_rows(str(folder), digests=True)
    digest = dtcstamp.content_digest(str(folder), entry_point=None)
    F.add_resource(g, name=name, resource_id=rid, packaging="directory", kind="image",
                   data={"url": "RB/lapidario", "content_digest": {"digest": digest, "files": len(rows)},
                         "members": []})
    F.add_members(g, rid, rows)
    return rid, digest


# ── 1 · implicit members ────────────────────────────────────────────────────

def test_the_members_of_a_directory_are_its_rows_and_no_node(tmp_path):
    lap = _photos(tmp_path)
    g = _graph()
    rid, digest = _directory(g, lap)
    files = F.resource_files(g, rid)
    assert len(files) == 18 and all(f["implicit"] and f["listed"] for f in files)
    assert not [n for n in g.nodes if n.node_type == "resource_file"]
    # the list IS the index: its digest is the folder's content digest
    rows = F.file_set_members(g, rid)
    assert dtcstamp.members_digest(rows) == digest
    # the transient node says where the file is and its digest
    one = files[0]
    assert one["node"].data["url"] == "RB/lapidario/" + one["path"]
    assert one["node"].data["checksum"].startswith("sha256:")
    assert F.directory_for_folder(g, str(lap)) == rid


def test_a_member_becomes_a_node_when_used_once(tmp_path):
    g = _graph()
    rid, digest = _directory(g, _photos(tmp_path))
    path = "Cat1/18390/IMG_002.jpg"
    out = F.materialize_member(g, rid, path, name="Architrave, fronte",
                               description="la foto della lettura")
    node = g.find_node_by_id(out["file_id"])
    assert out["created"] and node.node_type == "resource_file"
    assert node.name == "Architrave, fronte" and node.description == "la foto della lettura"
    assert node.data["url"] == f"RB/lapidario/{path}"
    # the transient id IS the id it gets: one file, one node
    before = next(f for f in F.resource_files(g, rid) if f["path"] == path)
    assert before["node"].node_id == node.node_id and not before["implicit"]
    assert len(F.resource_files(g, rid)) == 18           # each path once
    again = F.materialize_member(g, rid, path)
    assert again == {"file_id": node.node_id, "created": False}
    assert len([n for n in g.nodes if n.node_type == "resource_file"]) == 1
    # the row stays: the list is the index, its digest does not move
    assert len(F.member_rows(g, rid)) == 18
    assert dtcstamp.members_digest(F.file_set_members(g, rid)) == digest
    with pytest.raises(ValueError):
        F.materialize_member(g, rid, "nope.jpg")


def test_a_logical_group_keeps_its_paths_inside_and_draws_from_the_directory(tmp_path):
    g = _graph()
    rid, _ = _directory(g, _photos(tmp_path))
    g.add_node(__import__("s3dgraphy.nodes.stratigraphic_node", fromlist=["x"]).StratigraphicUnit("US1", "US1"))
    paths = ["Cat0/18380/IMG_000.jpg", "Cat0/18380/IMG_001.jpg", "Cat2/18401/IMG_002.jpg"]
    gid = S.make_group(g, name="US1 · fotogrammetria", members=paths, members_from=rid,
                       media_role="photogrammetry", link_to="US1")
    grp = g.find_node_by_id(gid)
    assert grp.data["packaging"] == "file_set" and grp.data["members_from"] == rid
    assert [r["path"] for r in grp.data["members"]] == sorted(paths)
    assert grp.data["checksum"].startswith("sha256:") and grp.data["digest_covers"] == "members"
    assert not [n for n in g.nodes if n.node_type == "resource_file"]
    files = F.resource_files(g, gid)
    assert [f["node"].data["url"] for f in files] == [f"RB/lapidario/{p}" for p in sorted(paths)]
    assert g.find_edge_by_id(f"US1__has_linked_resource__{gid}") is not None
    # materialized in the group: ONE node, held by the group and by the directory
    fid = F.materialize_member(g, gid, paths[0], name="la migliore")["file_id"]
    holders = sorted(e.edge_source for e in g.edges if e.edge_type == "has_file" and e.edge_target == fid)
    assert holders == sorted([gid, rid])
    # out of the group: the row and the edge go, the node stays (the directory holds it)
    out = F.remove_members(g, gid, [paths[0]])
    assert out == {"removed": 1, "edges": 1}
    assert g.find_node_by_id(fid) is not None
    assert len(F.resource_files(g, gid)) == 2
    with pytest.raises(ValueError):
        S.make_group(g, name="x", members=paths, members_from=rid, media_role="nessuno")


# ── 2 · roles ───────────────────────────────────────────────────────────────

def test_the_roles_base_and_of_the_project(tmp_path):
    g = _graph()
    ids = [r["id"] for r in MR.roles(g)]
    assert ids[:8] == ["photogrammetry", "frontispiece", "detail", "vector_drawing",
                       "raster_drawing", "model_3d", "orthophoto", "archival_documentation"]
    assert MR.add_local_role(g, "Frontespizio") == "frontispiece"      # the base answers
    lid = MR.add_local_role(g, "Calco in gesso", by="E.D.", at="2026-11-14T10:00:00Z")
    assert lid == "local:calco_in_gesso"
    row = MR.local_roles(g)[0]
    assert row["added_by"] == "E.D." and row["added_at"] == "2026-11-14T10:00:00Z"
    assert MR.add_local_role(g, "calco in gesso") == lid and len(MR.local_roles(g)) == 1
    assert MR.check_role(g, lid) == lid
    with pytest.raises(ValueError):
        MR.check_role(g, "local:altro")
    assert MR.label_of(g, "orthophoto", "it") == "ortofoto"


def test_the_roles_are_the_skos_module_of_stratigraph_templates():
    ttl = TEMPLATES / "vocabularies" / "skos" / "media-role.ttl"
    if not ttl.is_file():
        pytest.skip("stratigraph-templates is not next door")
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import SKOS
    gr = rdflib.Graph().parse(str(ttl), format="turtle")
    concepts = {str(s)[len(MR.NAMESPACE):]: {o.language: str(o) for o in gr.objects(s, SKOS.prefLabel)}
                for s in gr.subjects(rdflib.RDF.type, SKOS.Concept)}
    assert set(concepts) == set(MR.BASE_IDS)
    for i, it, en in MR.BASE_ROLES:
        assert (concepts[i]["it"], concepts[i]["en"]) == (it, en)


# ── 3 · sets inside sets ────────────────────────────────────────────────────

def test_has_sub_resource_in_the_datamodel():
    p = pathlib.Path(api.__file__).parent / "JSON_config" / "s3Dgraphy_connections_datamodel.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    e = d["edge_types"]["has_sub_resource"]
    assert e["reverse"]["name"] == "is_sub_resource_of"
    assert e["mapping"]["cidoc"] == "P106_is_composed_of"
    assert e["allowed_connections"] == {**e["allowed_connections"], "source": ["ResourceNode"],
                                        "target": ["ResourceNode"]}
    assert Graph.validate_connection("resource", "resource", "has_sub_resource")
    assert not Graph.validate_connection("resource", "resource_file", "has_sub_resource")


def test_split_by_folder_makes_the_tree_and_moves_the_rows(tmp_path):
    lap = _photos(tmp_path)
    g = _graph()
    rid, digest = _directory(g, lap)
    out = S.split_by_folder(g, rid, depth=2)
    assert len(out["created"]) == 3 + 6 and out["moved"] == 18 + 18
    cats = S.sub_resources(g, rid)
    assert [g.find_node_by_id(c).name for c in cats] == ["Cat0", "Cat1", "Cat2"]
    piece = S.sub_resources(g, cats[1])[0]
    pn = g.find_node_by_id(piece)
    assert pn.name == "18390" and pn.data["url"] == "RB/lapidario/Cat1/18390"
    # a piece's content digest is the one dtcstamp gives its folder
    assert pn.data["content_digest"]["digest"] == dtcstamp.content_digest(
        str(lap / "Cat1" / "18390"), entry_point=None)
    # nothing listed twice: the rows moved to the pieces
    assert F.member_rows(g, rid) == [] and F.member_rows(g, cats[1]) == []
    assert len(F.member_rows(g, piece)) == 3
    # the whole tree still gives the root's digest
    rows = S.tree_rows(g, rid)
    assert len(rows) == 18 and dtcstamp.members_digest(
        [{k: r[k] for k in ("path", "digest", "size_bytes")} for r in rows]) == digest
    tree = S.set_tree(g, rid)
    assert tree["files"] == 18 and [k["files"] for k in tree["children"]] == [6, 6, 6]
    # a second run adds nothing
    assert S.split_by_folder(g, rid, depth=2)["created"] == []
    # never a cycle
    with pytest.raises(ValueError):
        S.add_sub_resource(g, piece, rid)


def test_the_tree_survives_em_json_and_projects_to_rdf(tmp_path):
    g = _graph()
    rid, _ = _directory(g, _photos(tmp_path, cats=1, pieces=1, per=2))
    S.split_by_folder(g, rid, depth=1)
    doc = api.graph_to_emjson(g)
    g2, _ = api.load_emjson(json.loads(json.dumps(doc)))
    e = [x for x in g2.edges if x.edge_type == "has_sub_resource"][0]
    assert e.attributes.get("path") == "Cat0"
    cat = g2.find_node_by_id(e.edge_target)
    assert [r["path"] for r in cat.data["members"]] == ["18380/IMG_000.jpg", "18380/IMG_001.jpg"]
    ttl = api.emjson_to_ttl(doc)
    assert "P106_is_composed_of" in ttl and "hadMember" in ttl


# ── 4 · the catalogue ───────────────────────────────────────────────────────

def _catalogue(tmp_path):
    g = _graph()
    rid, _ = _directory(g, _photos(tmp_path))
    S.split_by_folder(g, rid, depth=2, names={"Cat1": "Architravi"})
    g.add_node(DocumentNode("D30", name="D.30", description="Catalogo del lapidario della Basilica Iulia"))
    g.add_edge("D30__has_linked_resource__lap", "D30", rid, "has_linked_resource")
    return g, rid


def test_an_open_catalogue_counts_live_and_cites_its_entries(tmp_path):
    g, rid = _catalogue(tmp_path)
    assert CAT.is_catalogue(g, "D30") and CAT.catalogue_root(g, "D30") == rid
    assert CAT.catalogue_state(g, "D30")["state"] == "undated"
    st = CAT.open_catalogue(g, "D30", start=2024)
    assert (st["state"], st["start"], st["end"], st["live"]) == ("open", 2024.0, None, True)
    assert (st["entries"], st["sections"], st["files"]) == (6, 3, 18)
    entries = CAT.catalogue_entries(g, "D30")
    assert [e["path"] for e in entries][:2] == ["Cat0/18380", "Cat0/18381"]
    arch = [e for e in entries if e["path"].startswith("Cat1/")][0]
    assert arch["citation"] == "D.30 · 18390" and CAT.cite(g, arch["id"]) == "D.30 · 18390"
    assert CAT.cite(g, rid) == "D.30"
    assert g.find_node_by_id(S.sub_resources(g, rid)[1]).name == "Architravi"
    # live: a photograph more in a piece is counted at once
    F.add_members(g, arch["id"], [{"path": "IMG_009.jpg", "digest": "sha256:" + "a" * 64, "size_bytes": 3}])
    assert CAT.catalogue_state(g, "D30")["files"] == 19


def test_a_closed_catalogue_keeps_the_counts_of_its_stamp(tmp_path):
    g, rid = _catalogue(tmp_path)
    CAT.open_catalogue(g, "D30", start=2024)
    st = CAT.close_catalogue(g, "D30", end=2026, by="E.D.", at="2026-11-14T12:00:00Z")
    assert (st["state"], st["end"], st["live"], st["files"]) == ("closed", 2026.0, False, 18)
    stamp = g.find_node_by_id("D30").data["catalog_stamp"]
    assert stamp["members_digest"] == g.find_node_by_id(rid).data["content_digest"]["digest"]
    assert stamp["by"] == "E.D." and stamp["entries"] == 6
    piece = CAT.catalogue_entries(g, "D30")[0]["id"]
    F.add_members(g, piece, [{"path": "late.jpg", "digest": "sha256:" + "b" * 64}])
    assert CAT.catalogue_state(g, "D30")["files"] == 18          # final
    # an end without a stamp is said as such
    g.find_node_by_id("D30").data.pop("catalog_stamp")
    assert CAT.catalogue_state(g, "D30")["state"] == "ended_unstamped"


def test_an_entry_inherits_the_catalogue_unless_it_has_its_own(tmp_path):
    g, rid = _catalogue(tmp_path)
    CAT.open_catalogue(g, "D30", start=2024)
    g.add_node(AuthorNode("A1", name="Paola", surname="Rossi"))
    g.add_edge("D30__has_author__A1", "D30", "A1", "has_author")
    piece = CAT.catalogue_entries(g, "D30")[2]["id"]
    r = resolve_provenance(g, piece, get_rule("absolute_time_start"))
    assert (r["value"], r["level"], r["origin"]) == (2024.0, "set", "D30")
    assert r["chain"][0] == piece and r["chain"][-1] == "D30"
    a = resolve_provenance(g, piece, get_rule("author"))
    assert a["origin"] == "A1" or a["origin"] == "D30"
    assert a["level"] == "set" and "Rossi" in a["value"]
    # a file of a piece, once a node: the piece, then the catalogue
    fid = F.materialize_member(g, piece, F.member_rows(g, piece)[0]["path"])["file_id"]
    rf = resolve_provenance(g, fid, get_rule("absolute_time_start"))
    assert (rf["value"], rf["level"]) == (2024.0, "set") and rf["chain"][-1] == "D30"
    # its own
    g.add_node(AuthorNode("A2", name="Marco", surname="Bianchi"))
    g.add_edge("p__has_author__A2", piece, "A2", "has_author")
    own = resolve_provenance(g, piece, get_rule("author"))
    assert own["level"] == "node" and "Bianchi" in own["value"]


# ── 5 · Metashape: the folder and its rows ──────────────────────────────────

def test_metashape_writes_the_folder_with_its_rows_and_no_photo_node(tmp_path):
    from test_metashape_project import build
    from s3dgraphy.importer.metashape_project import metashape_to_dtc, read_metashape_project
    project = read_metashape_project(str(build(tmp_path)))
    g = Graph("g")
    out = metashape_to_dtc(project, g)
    assert sorted(a["members"] for a in out["acquisitions"]) == [2, 3]
    assert not [n for n in g.nodes if n.node_type == "resource_file"]
    drone = [g.find_node_by_id(a["sets"][0]) for a in out["acquisitions"] if a["sensor"].startswith("FC300X")][0]
    assert drone.data["packaging"] == "directory"
    assert drone.data["content_digest"]["digest"] == dtcstamp.content_digest(
        str(tmp_path / "Segni_Acropoli_drone"), entry_point=None)
    rows = drone.data["members"]
    assert [r["path"] for r in rows] == ["DJI_0170.JPG", "DJI_0171.JPG", "DJI_0172.JPG"]
    assert all(r.get("camera_label") and r.get("digest") for r in rows)
    # the folder met again is that directory (D7), and nothing is added
    n = (len(g.nodes), len(g.edges))
    metashape_to_dtc(project, g)
    assert (len(g.nodes), len(g.edges)) == n
    # a photograph used becomes a node, with what the project said of it
    fid = F.materialize_member(g, drone.node_id, "DJI_0171.JPG")["file_id"]
    node = g.find_node_by_id(fid)
    assert node.data["camera_label"] == rows[1]["camera_label"]
    assert node.data["checksum"] == rows[1]["digest"]


def test_a_reading_on_a_photograph_of_an_entry_cites_the_catalogue(tmp_path):
    """The piece is an entry, not a document: a region on one of its photographs
    makes the extractor cite D.30, and no document is minted for the piece."""
    from s3dgraphy.annotation.paradata import create_annotation_paradata
    from s3dgraphy.nodes.stratigraphic_node import StratigraphicUnit
    g, rid = _catalogue(tmp_path)
    g.add_node(StratigraphicUnit("SF1", "SF1"))
    piece = CAT.catalogue_entries(g, "D30")[3]["id"]
    fid = F.materialize_member(g, piece, F.member_rows(g, piece)[0]["path"])["file_id"]
    docs = len([n for n in g.nodes if n.node_type == "document"])
    res = create_annotation_paradata(g, fid, {"shape_kind": "rect", "rect": [0.1, 0.1, 0.3, 0.3]},
                                     "altezza 0.62 m", "height", target_unit_id="SF1")
    assert res.source_document_id == "D30"
    assert len([n for n in g.nodes if n.node_type == "document"]) == docs
    assert any(e.edge_type == "extracted_from" and e.edge_target == "D30" for e in g.edges)
