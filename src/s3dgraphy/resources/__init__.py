"""Resource layer (R0) — the data-plane seam.

Separates a resource's **identity/provenance** from its **storage**. Consumers
never reference a raw path or object key directly; they hold a **stable,
storage-agnostic resource ID** and ask a **resolver** to map it to a concrete
:class:`Location` (a filesystem path, a ``file://`` / ``s3://`` URI, or an
``http(s)`` URL).

R0 establishes the SEAM only:

  * The **stable resource ID** is the ``ResourceNode``'s node UUID (``node_id``).
    This is ADDITIVE — no datamodel change, no ``ResourceNode → ResourceNode``
    rename. The ResourceNode's ``url`` is treated as the *current locator*, NOT as
    the resource's identity.
  * A pluggable **backend registry** (:class:`ResolverRegistry`) with ONE
    default backend, :class:`PassthroughBackend`, which resolves a resource to
    its stored locator (the ResourceNode ``url``) — so existing graphs resolve
    unchanged. Real storage backends (R1 FS-index, R2 MinIO) plug in later by
    registering ahead of the passthrough fallback.

No web framework, no network, no hardcoded EM vocab lists here. See
:mod:`s3dgraphy.resources.resolver`.
"""

from .resolver import (
    LOCATION_KINDS,
    Location,
    PassthroughBackend,
    ResolverRegistry,
    ResourceBackend,
    classify_locator,
    default_registry,
    stable_resource_id,
)
from .fs_backend import (
    DOSCO_NODE_TYPES,
    FSIndexBackend,
    ManifestEntry,
    Orphan,
    ScanResult,
    classify_resource_type,
    em_id_of,
)
from .minio_backend import (
    MinioBackend,
    MinioConfig,
    MinioEntry,
)

__all__ = [
    "LOCATION_KINDS",
    "Location",
    "ResourceBackend",
    "PassthroughBackend",
    "ResolverRegistry",
    "classify_locator",
    "default_registry",
    "stable_resource_id",
    # R1 — FS-index backend
    "FSIndexBackend",
    "ManifestEntry",
    "ScanResult",
    "Orphan",
    "classify_resource_type",
    "DOSCO_NODE_TYPES",
    "em_id_of",
    # R2 — MinIO / S3 backend (optional 'minio' extra)
    "MinioBackend",
    "MinioConfig",
    "MinioEntry",
]
