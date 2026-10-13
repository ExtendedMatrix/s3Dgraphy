"""Publishing a proxy's .glb keeps it a proxy (MICRO il proxy arriva come
proprietà, 2026-10-13).

EMtools publishes the glb of a unit's proxy into the room with
``promote_resource(media_type="model/gltf-binary")``. The media type says only
«a 3D model»; the resource already says more — ``proxy_model``, the genre
``create_geometry_proxy`` gave it — and writing ``3d_model`` over it made the
proxy a file its own chain no longer found (``linked_proxy_resources``).
"""

from s3dgraphy.geometry import linked_proxy_resources
from s3dgraphy.geometry.proxy import create_geometry_proxy, proxy_resource_id
from s3dgraphy.graph import Graph
from s3dgraphy.nodes import StratigraphicUnit
from s3dgraphy.publication import promote_resource

DIGEST = "sha256:" + "ab" * 32


def _graph_with_proxy():
    g = Graph(graph_id="promote-proxy")
    g.add_node(StratigraphicUnit("US3", name="US3"))
    result = create_geometry_proxy(g, "US3", {"url": "proxies/US3.glb"})
    return g, result


def test_a_published_proxy_glb_stays_proxy_model():
    g, proxy = _graph_with_proxy()
    promote_resource(g, proxy.resource_id, url=f"https://room/assets/{DIGEST}",
                     sha256=DIGEST, media_type="model/gltf-binary",
                     residency="resident")
    resource = g.find_node_by_id(proxy.resource_id)
    assert resource.data["url_type"] == "proxy_model"
    assert resource.data["checksum"] == DIGEST
    assert resource.data["media_type"] == "model/gltf-binary"
    assert [r.node_id for r in linked_proxy_resources(g, proxy.shape_id)] == \
        [proxy_resource_id(proxy.shape_id)]


def test_a_plain_resource_still_learns_3d_model_from_the_media_type():
    g = Graph(graph_id="promote-plain")
    promote_resource(g, "R1", url=f"https://room/assets/{DIGEST}", sha256=DIGEST,
                     media_type="model/gltf-binary")
    assert g.find_node_by_id("R1").data["url_type"] == "3d_model"
