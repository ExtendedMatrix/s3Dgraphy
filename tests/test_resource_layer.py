"""R0 — Resource-layer core: the stable-ID resolver seam.

Verifies (per the R0 DoD): a resource has a stable ID (its node UUID); the
default passthrough backend resolves a resource to a Location; existing
url/path-based LinkNodes resolve unchanged; the backend registry accepts a
second backend so R1/R2 can plug in; and the seam pulls no web deps.
"""

import sys

import pytest

from s3dgraphy import api
from s3dgraphy.graph import Graph
from s3dgraphy.nodes.resource_node import ResourceNode
from s3dgraphy.resources import (
    Location,
    PassthroughBackend,
    ResolverRegistry,
    ResourceBackend,
    classify_locator,
    default_registry,
    stable_resource_id,
)


def _graph_with(*link_nodes):
    g = Graph(graph_id="g")
    for n in link_nodes:
        g.add_node(n)
    return g


# ── stable ID ─────────────────────────────────────────────────────────────────
def test_stable_id_is_node_uuid():
    n = ResourceNode(node_id="res-uuid-123", name="R", url="/a/b.jpg")
    assert stable_resource_id(n) == "res-uuid-123" == n.node_id


# ── locator classification ─────────────────────────────────────────────────────
@pytest.mark.parametrize("locator,kind", [
    ("/abs/path/model.glb", "local_path"),
    ("relative/dir/img.png", "local_path"),
    ("file:///abs/path/doc.pdf", "file_uri"),
    ("s3://bucket/key.obj", "s3_uri"),
    ("http://example.org/x", "http_url"),
    ("https://zenodo.org/record/1", "http_url"),
    ("", "local_path"),
])
def test_classify_locator(locator, kind):
    assert classify_locator(locator) == kind


# ── passthrough resolution ─────────────────────────────────────────────────────
def test_resolve_via_passthrough_backend():
    n = ResourceNode(node_id="r1", name="Zenodo", url="https://zenodo.org/record/28917")
    g = _graph_with(n)
    loc = api.resolve_resource(g, "r1")
    assert loc == {"kind": "http_url", "value": "https://zenodo.org/record/28917",
                   "exists": None}


def test_existing_url_linknode_resolves_unchanged():
    # a plain url/path ResourceNode (what every current graph holds) resolves to its
    # locator verbatim — non-breaking.
    n = ResourceNode(node_id="r2", name="Img", url="http://aton.ispc.it/image.jpeg")
    g = _graph_with(n)
    loc = api.resolve_resource(g, "r2")
    assert loc["value"] == "http://aton.ispc.it/image.jpeg"
    assert loc["kind"] == "http_url"


def test_local_path_existence_is_checked(tmp_path):
    f = tmp_path / "asset.obj"
    f.write_text("x")
    present = ResourceNode(node_id="present", name="A", url=str(f))
    missing = ResourceNode(node_id="missing", name="B", url=str(tmp_path / "nope.obj"))
    g = _graph_with(present, missing)
    assert api.resolve_resource(g, "present")["exists"] is True
    assert api.resolve_resource(g, "missing")["exists"] is False


def test_resolve_unknown_resource_is_none():
    g = _graph_with(ResourceNode(node_id="r", name="R", url="/x"))
    assert api.resolve_resource(g, "does-not-exist") is None


# ── list / register ────────────────────────────────────────────────────────────
def test_list_resources_lists_linknodes_only():
    n = ResourceNode(node_id="lr", name="Doc", url="/docs/a.pdf")
    g = _graph_with(n)
    resources = api.list_resources(g)
    ids = {r["id"] for r in resources}
    assert "lr" in ids  # the geo_position node the Graph auto-adds is excluded
    entry = next(r for r in resources if r["id"] == "lr")
    assert entry == {"id": "lr", "name": "Doc", "locator": "/docs/a.pdf",
                     "kind": "local_path"}


def test_register_resource_assigns_stable_id_and_stores_locator():
    g = Graph(graph_id="g")
    out = api.register_resource(g, "/store/new.glb", name="New")
    assert out["locator"] == "/store/new.glb" and out["kind"] == "local_path"
    node = g.find_node_by_id(out["id"])
    assert isinstance(node, ResourceNode) and node.url == "/store/new.glb"
    # the assigned ID is the stable resource identity → resolvable immediately
    assert api.resolve_resource(g, out["id"])["value"] == "/store/new.glb"


def test_register_resource_honours_explicit_id():
    g = Graph(graph_id="g")
    out = api.register_resource(g, "/x", resource_id="fixed-id")
    assert out["id"] == "fixed-id"


# ── pluggable registry (proves R1/R2 can plug in) ──────────────────────────────
class _StubBackend(ResourceBackend):
    """A stand-in for a future FS-index / S3 backend that OWNS certain IDs."""
    name = "stub"

    def __init__(self, owned):
        self.owned = owned

    def resolve(self, resource_id, locator, *, graph=None):
        if resource_id in self.owned:
            return Location(kind="s3_uri", value=f"s3://bucket/{resource_id}",
                            exists=None)
        return None  # not ours → fall through to passthrough


def test_registry_accepts_second_backend_ahead_of_passthrough():
    reg = default_registry()
    reg.register(_StubBackend(owned={"owned-1"}), priority=10)
    # higher-priority backend is tried first
    assert [b.name for b in reg.backends()] == ["stub", "passthrough"]

    n_owned = ResourceNode(node_id="owned-1", name="O", url="/local/orig.obj")
    n_other = ResourceNode(node_id="other-1", name="P", url="/local/other.obj")
    g = _graph_with(n_owned, n_other)

    owned = api.resolve_resource(g, "owned-1", registry=reg)
    other = api.resolve_resource(g, "other-1", registry=reg)
    # the stub backend claimed the resource it owns...
    assert owned == {"kind": "s3_uri", "value": "s3://bucket/owned-1", "exists": None}
    # ...and everything else falls through to the passthrough locator (unchanged)
    assert other == {"kind": "local_path", "value": "/local/other.obj", "exists": False}


def test_passthrough_is_the_default_and_only_r0_backend():
    reg = default_registry()
    assert [b.name for b in reg.backends()] == ["passthrough"]
    assert isinstance(reg.backends()[0], PassthroughBackend)


# ── no web deps on the seam ────────────────────────────────────────────────────
def test_resource_layer_pulls_no_web_deps():
    import importlib
    importlib.import_module("s3dgraphy.resources")
    for mod in ("fastapi", "uvicorn", "starlette"):
        assert mod not in sys.modules
