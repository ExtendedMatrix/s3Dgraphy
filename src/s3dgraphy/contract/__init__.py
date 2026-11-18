"""The adapter contract — one shape, two consumers.

:mod:`~s3dgraphy.contract.core` is the contract: a descriptor, a registry, an
invocation with four refusals, and a DTC-attributed delta as the result.
:mod:`~s3dgraphy.contract.connector` specialises it for connectors (Blender,
viewers, imports, database syncs); the field assistant's `ToolRegistry`
specialises it for tools. Neither owns it.

Two directions, one contract. :mod:`~s3dgraphy.contract.connector` guards what
comes IN (a write passes the seam, attributed); :mod:`~s3dgraphy.contract.consumer`
serves what goes OUT (a read-only connector is granted, rights-aware, tombstones
and proposals dropped). :mod:`~s3dgraphy.contract.reference` holds the descriptors
whose adapter belongs to another team — the spec they implement against.
"""

from .core import (CONTRACT_NAMESPACE, DELTA_OPS, Delta, Descriptor, Handler,
                   REFUSALS, Refusals, Registry, Result, Slot, invoke, stable_id)
from .connector import (CAPABILITIES, CAPABILITY_LAYER, CAPABILITY_LAYERS,
                        CONNECTOR_API_VERSION, ConnectorDescriptor,
                        ConnectorRegistry, HOSTS, OPS_SINCE, SEAM, SEAM_IT,
                        SeamRefusals, TRANSPORTS, Versions, VOLATILE_KEY,
                        WRITING_CAPABILITIES, apply_delta, apply_delta_to_graph,
                        bake, current_versions, document_view, guard_write,
                        handshake, speaks_ops, validate_delta, validate_ops)
from .consumer import (CONSUMER_CAPABILITIES, READ_CAPABILITIES, ROLES,
                       SERVE, VISIBILITIES, PublishedCount, ServeRefusals,
                       Subscription, granted, is_consumer, may_read,
                       published_view, push, role_can_write, role_rank, serve,
                       serve_asset, serve_graph, subscribe)
from .reference import (HERIVERSE_CAPABILITIES, HERIVERSE_TRANSPORT, heriverse,
                        heriverse_wire)

__all__ = [
    "CONTRACT_NAMESPACE", "DELTA_OPS", "Delta", "Descriptor", "Handler", "REFUSALS",
    "Refusals", "Registry", "Result", "Slot", "invoke", "stable_id",
    "CAPABILITIES", "CAPABILITY_LAYER", "CAPABILITY_LAYERS",
    "CONNECTOR_API_VERSION", "ConnectorDescriptor", "ConnectorRegistry",
    "HOSTS", "TRANSPORTS", "Versions", "WRITING_CAPABILITIES",
    "VOLATILE_KEY", "apply_delta", "bake", "current_versions",
    "document_view", "guard_write", "handshake", "validate_delta",
    # connector API 1.1 (MICRO-PL01): ops, a live Graph, the seam's words in IT
    "OPS_SINCE", "SEAM", "SEAM_IT", "SeamRefusals", "apply_delta_to_graph",
    "speaks_ops", "validate_ops",
    # the outgoing direction: a consumer is SERVED
    "CONSUMER_CAPABILITIES", "READ_CAPABILITIES", "ROLES", "SERVE",
    "VISIBILITIES", "PublishedCount", "ServeRefusals", "Subscription",
    "granted", "is_consumer", "may_read", "published_view", "push",
    "role_can_write", "role_rank", "serve", "serve_asset", "serve_graph",
    "subscribe",
    # reference descriptors (the spec a partner implements against)
    "HERIVERSE_CAPABILITIES", "HERIVERSE_TRANSPORT", "heriverse",
    "heriverse_wire",
]
