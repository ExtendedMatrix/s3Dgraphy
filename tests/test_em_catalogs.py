"""``em.catalogs`` — the datamodel's catalogues in ``em``, read only (MICRO-SEG09).

E.D., 21 Nov 2026: «ci sono tutti i data object di s3dgraphy?». Defended:

* every catalogue of ``JSON_config`` the MICRO names is reachable from ``em``
  (qualia, document and extractor types, visual rules, colour ramps, palette
  icons, state symbols, alternative cases), with the node and edge types;
* the node types are the 68 classes of ``reference/types`` (one page each),
  the edge types its 63;
* what a script gets is a COPY: changing it changes nothing in the datamodel;
* ``em.profiles.document_types()`` exists beside ``qualia_types`` and
  ``extractor_types`` (core + the active packages);
* the reference has a page for ``em.catalogs``.
"""

import json
from pathlib import Path

from s3dgraphy import em
from s3dgraphy.datamodel import JSON_CONFIG

ROOT = Path(__file__).resolve().parent.parent


def test_every_catalogue_the_micro_names_is_there():
    names = em.catalogs.names()
    for n in ("node_types", "edge_types", "qualia_types", "document_types", "extractor_types",
              "visual_rules", "color_ramps", "palette_icons", "state_symbols", "alternative_cases"):
        assert n in names, n
        assert getattr(em.catalogs, n)(), f"{n} is empty"
    for n, d in em.catalogs.describe().items():
        assert (JSON_CONFIG / d["file"]).is_file(), d["file"]
        assert callable(getattr(em.catalogs, n))


def test_node_and_edge_types_match_the_reference():
    nodes = em.catalogs.node_types()
    edges = em.catalogs.edge_types()
    pages_n = {p.stem for p in (ROOT / "docs-api/reference/types/nodes").glob("*.rst")}
    pages_e = {p.stem for p in (ROOT / "docs-api/reference/types/edges").glob("*.rst")}
    assert len(nodes) == 68 and len(edges) == 63
    assert len(pages_n) == len(nodes) and len(pages_e) == len(edges)
    assert nodes["StratigraphicUnit"]["node_type"] == "US"
    assert nodes["DTCNode"]["node_type"] is None          # abstract: no node_type
    assert edges["is_after"]["reverse"]["name"] == "is_before"


def test_the_catalogues_say_what_the_files_say():
    raw = json.loads((JSON_CONFIG / "em_color_ramps.json").read_text(encoding="utf-8"))
    assert em.catalogs.color_ramps() == raw["ramps"]
    raw = json.loads((JSON_CONFIG / "em_state_symbols.json").read_text(encoding="utf-8"))
    assert em.catalogs.state_symbols() == raw
    q = em.catalogs.qualia_types()
    assert q and all(v.get("origin") == "core" and v.get("category") for v in q.values())
    assert set(em.catalogs.versions()["versions"]) >= {"nodes", "connections", "qualia", "visual_rules"}


def test_a_copy_changes_nothing():
    for n in em.catalogs.names():
        v = getattr(em.catalogs, n)()
        v.clear()
        assert getattr(em.catalogs, n)(), f"{n}: clearing the copy emptied the catalogue"
    nt = em.catalogs.node_types()
    nt["StratigraphicUnit"]["node_type"] = "X"
    assert em.catalogs.node_types()["StratigraphicUnit"]["node_type"] == "US"


def test_profiles_document_types():
    d = em.profiles.document_types()
    assert set(em.catalogs.document_types()) <= set(d)


def test_the_reference_has_its_page():
    page = (ROOT / "docs-api/reference/em/catalogs.rst").read_text(encoding="utf-8")
    assert "automodule:: s3dgraphy.em.catalogs" in page
    assert "em/catalogs" in (ROOT / "docs-api/reference/index.rst").read_text(encoding="utf-8")
