"""Several addresses for one resource (dev27, A4; E.D. 2026-10-01).

Same bytes, same digest: one resource with several addresses. Every guard on a
case that makes it fire:

* two addresses, one digest → one resource; the url stays address 0;
* a different digest is refused (a sister resource), and so is a resource with
  no digest;
* an address marked dead does not remove the resource, nor the address;
* ``promote_resource`` keeps the disk path when the bytes are the same;
* ``snapshot_uri`` gives a reference a dated digest — from a local fake server,
  nothing is downloaded from the network;
* in RDF every locator is an ``rdfs:seeAlso``, and the round trip is identical.
"""

from __future__ import annotations

import hashlib
import http.server
import threading

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.resources.addresses import AddressError, live_addresses

BYTES = b"%PDF-1.4 vitruvio"
DIGEST = "sha256:" + hashlib.sha256(BYTES).hexdigest()
OTHER = "sha256:" + hashlib.sha256(b"another scan").hexdigest()


def _pdf(**kw):
    return ResourceNode("scan", "vitruvio.pdf", url="scans/vitruvio.pdf",
                        checksum=DIGEST, residency="resident", **kw)


def test_two_addresses_one_digest_one_resource():
    r = _pdf()
    out = api.add_address(r, "s3://em/" + DIGEST[7:], checksum=DIGEST,
                          residency="resident")
    assert [a["locator"] for a in out] == ["scans/vitruvio.pdf",
                                           "s3://em/" + DIGEST[7:]]
    assert out[0]["primary"] and not out[1]["primary"]
    assert r.data["url"] == "scans/vitruvio.pdf"       # what Heriverse reads
    # the same address twice changes nothing
    assert len(api.add_address(r, "s3://em/" + DIGEST[7:], checksum=DIGEST)) == 2


def test_a_resource_of_one_address_looks_as_it_always_did():
    r = _pdf()
    assert api.addresses(r) == [{"locator": "scans/vitruvio.pdf",
                                 "residency": "resident", "primary": True}]
    assert "addresses" not in r.data


def test_another_digest_is_a_sister_not_an_address():
    r = _pdf()
    with pytest.raises(AddressError, match="sister resource"):
        api.add_address(r, "zenodo/other.pdf", checksum=OTHER)
    with pytest.raises(AddressError, match="digest of the bytes"):
        api.add_address(r, "zenodo/other.pdf")
    bare = ResourceNode("page", "page", url="https://example.org/p")
    with pytest.raises(AddressError, match="no digest"):
        api.add_address(bare, "https://mirror.example.org/p", checksum=DIGEST)
    assert "addresses" not in r.data and "addresses" not in bare.data


def test_a_dead_address_does_not_remove_the_resource():
    r = _pdf()
    api.add_address(r, "https://zenodo.org/x.pdf", checksum=DIGEST)
    out = api.check_address(r, "scans/vitruvio.pdf", ok=False,
                            at="2026-10-31T09:00:00Z")
    assert out["live"] == 1 and "1 other address" in out["warning"]
    assert [a["locator"] for a in api.addresses(r)] == [
        "scans/vitruvio.pdf", "https://zenodo.org/x.pdf"]
    assert [a["locator"] for a in live_addresses(r)] == ["https://zenodo.org/x.pdf"]
    out = api.check_address(r, "https://zenodo.org/x.pdf", ok=False)
    assert out["live"] == 0 and "no address" in out["warning"]
    assert len(api.addresses(r)) == 2                  # still there, both


def test_promote_keeps_the_disk_path_of_the_same_bytes():
    g = Graph("g")
    g.add_node(_pdf())
    api.promote_resource(g, "scan", url="https://room/assets/" + DIGEST[7:],
                         sha256=DIGEST, residency="resident")
    r = g.find_node_by_id("scan")
    assert r.data["url"] == "https://room/assets/" + DIGEST[7:]
    assert [a["locator"] for a in api.addresses(r)] == [
        "https://room/assets/" + DIGEST[7:], "scans/vitruvio.pdf"]


def test_promote_without_a_digest_before_keeps_nothing_it_cannot_prove():
    g = Graph("g")
    g.add_node(ResourceNode("scan", "vitruvio.pdf", url="scans/vitruvio.pdf"))
    api.promote_resource(g, "scan", url="https://room/a", sha256=DIGEST)
    assert [a["locator"] for a in api.addresses(g.find_node_by_id("scan"))] == [
        "https://room/a"]


# ── snapshot_uri, from a fake server on localhost ────────────────────────────

class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(BYTES)

    def log_message(self, *args):
        pass


@pytest.fixture()
def page_url():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/vitruvius/3.html"
    server.shutdown()


def test_snapshot_gives_a_reference_a_dated_digest(page_url, tmp_path):
    r = ResourceNode("page", "Vitruvio III online", url=page_url,
                     residency="reference")
    out = api.snapshot_uri(r, at="2026-10-31T09:00:00Z",
                           save_to=str(tmp_path / "page.html"))
    assert out["checksum"] == DIGEST and r.data["checksum"] == DIGEST
    assert r.data["checksum_at"] == "2026-10-31T09:00:00Z"
    assert (tmp_path / "page.html").read_bytes() == BYTES
    locs = [(a["locator"], a.get("residency")) for a in api.addresses(r)]
    assert locs == [(page_url, "reference"), (str(tmp_path / "page.html"), "resident")]
    with pytest.raises(AddressError, match="already has its digest"):
        api.snapshot_uri(r)


def test_a_failed_snapshot_writes_nothing():
    r = ResourceNode("page", "p", url="http://127.0.0.1:9/none")

    def broken(_url):
        raise OSError("connection refused")
    with pytest.raises(OSError):
        api.snapshot_uri(r, fetch=broken)
    assert "checksum" not in r.data


# ── RDF ──────────────────────────────────────────────────────────────────────

rdflib = pytest.importorskip("rdflib")
from rdflib import Literal, URIRef  # noqa: E402
from rdflib.namespace import RDFS  # noqa: E402

from s3dgraphy.exporter.emjson_exporter import build_emjson  # noqa: E402
from s3dgraphy.exporter.rdf_exporter import RDFExporter  # noqa: E402
from s3dgraphy.importer.emjson_importer import parse_emjson  # noqa: E402
from s3dgraphy.importer.rdf_importer import RDFImporter  # noqa: E402


def test_in_rdf_every_address_is_a_see_also_and_comes_back(tmp_path):
    g = Graph("g")
    r = _pdf()
    g.add_node(r)
    api.add_address(r, "https://zenodo.org/x.pdf", checksum=DIGEST)
    api.check_address(r, "scans/vitruvio.pdf", ok=False, at="2026-10-31T09:00:00Z")
    r.data["checksum_at"] = "2026-10-30T08:00:00Z"
    first, _ = parse_emjson(build_emjson(g))
    exporter = RDFExporter(str(tmp_path / "g.ttl"), format="turtle")
    path = exporter.export_single_graph(first)
    store = rdflib.Graph()
    store.parse(path, format="turtle")
    iri = exporter._node_iri(g.graph_id, "scan")
    assert set(store.objects(iri, RDFS.seeAlso)) == {
        Literal("scans/vitruvio.pdf"), URIRef("https://zenodo.org/x.pdf")}
    back = RDFImporter().parse(path)[0]
    again, _ = parse_emjson(build_emjson(back))
    got = again.find_node_by_id("scan").data
    want = first.find_node_by_id("scan").data
    for key in ("url", "addresses", "checksum", "checksum_at", "residency"):
        assert got.get(key) == want.get(key), key
