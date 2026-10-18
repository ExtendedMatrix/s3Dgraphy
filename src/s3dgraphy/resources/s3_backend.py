"""S3 resource backend (R2) — the object-storage tier of the Resource
layer. Pure ops, no web framework; the S3 client is an OPTIONAL, lazily-imported
dependency.

Mirrors :mod:`s3dgraphy.resources.fs_backend` (R1) — same
:class:`~s3dgraphy.resources.resolver.ResourceBackend` interface, same **stable-ID**
concept (a resource has ONE id whether it lives on the file system or in the S3
store), a
parallel **manifest** mapping ``stable id ↔ object key``. Register it with a
:class:`~s3dgraphy.resources.resolver.ResolverRegistry` at a priority ABOVE the
passthrough fallback so IDs it owns resolve to ``s3://…`` Locations.

  * :meth:`S3Backend.ingest` uploads a file, mints/reuses a stable ID, records
    ``id → object_key`` in the manifest, and returns ``(stable_id, object_key)``.
  * :meth:`S3Backend.resolve` returns an ``s3_uri`` :class:`Location` from the
    manifest with NO network I/O.
  * :meth:`S3Backend.presign` (explicit, network) returns a short-lived
    ``http_url`` Location via a presigned GET.

The default config targets a LOCAL S3-compatible store (``localhost:9000``,
path-style, insecure — RustFS in the dev stack) — the same convention
Heriverse-Server uses; point ``endpoint`` at a cloud S3 endpoint to promote the
same backend online (no code change). Bundling / launching a local store is
deploy/ops (WP6), out of scope here.

The S3 SDK (``boto3``) is an optional extra (``s3dgraphy[s3]``): it is imported
lazily and its absence raises :class:`s3dgraphy.api.MissingDependency` (same
contract as rdflib for TTL), so ``import s3dgraphy.resources`` / ``s3dgraphy.api``
stay S3-dep-free.

The client (:func:`make_client`) is configured for an S3-compatible server that
is not Amazon: **path-style** addressing (the bucket in the path, not in the host
name — which also makes presigned URLs work against a local store), SigV4, the
region ``us-east-1`` unless one is named, checksums only when an operation
requires them (botocore >= 1.36 otherwise adds a CRC trailer not every server
speaks), no proxy from the environment, bounded timeouts and a few retries.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from .fs_backend import classify_resource_type
from .resolver import Location, ResourceBackend


#: The region a client signs with when nobody names one: the one S3-compatible
#: servers accept, and the one where CreateBucket takes no LocationConstraint.
DEFAULT_REGION = "us-east-1"

#: Seconds to open a connection / between two reads on an open one.
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 60.0

#: Attempts per call, the first included (``standard`` retry mode).
MAX_ATTEMPTS = 3

#: The ways an S3 server says «there is no such thing»: a HEAD has no body, so a
#: missing object answers the bare status (``404``); a GET carries the S3 code.
NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NotFound",
                             "NoSuchBucket", "404"})


def endpoint_url(config: "S3Config") -> str:
    """``scheme://host[:port]`` — the host from ``endpoint``, the scheme from
    ``secure``."""
    host = str(config.endpoint).split("://", 1)[-1].rstrip("/")
    return f"{'https' if config.secure else 'http'}://{host}"


def make_client(config: "S3Config") -> Any:
    """A ``boto3`` S3 client for ``config``, configured as the module docstring
    says. Raises :class:`ImportError` when ``boto3`` is not installed — the
    caller says what that means for it."""
    import boto3  # type: ignore
    from botocore.config import Config  # type: ignore

    options: Dict[str, Any] = dict(
        signature_version="s3v4",
        s3={"addressing_style": "path" if config.force_path_style else "auto"},
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=READ_TIMEOUT,
        retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
        proxies={},
    )
    try:
        cfg = Config(request_checksum_calculation="when_required",
                     response_checksum_validation="when_required", **options)
    except TypeError:     # botocore < 1.36: no such options, and no CRC trailers
        cfg = Config(**options)
    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint_url(config),
        aws_access_key_id=config.access_key,
        aws_secret_access_key=config.secret_key,
        region_name=config.region or DEFAULT_REGION,
        config=cfg,
    )


def error_code(exc: BaseException) -> str:
    """The S3 error code of a ``ClientError`` (``NoSuchKey``, ``404``…), or ""
    for anything that is not an answer from the store."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    return str((response.get("Error") or {}).get("Code") or "")


def is_not_found(exc: BaseException) -> bool:
    """Did the store ANSWER «no such object / bucket»? A network failure carries
    no answer and is never read as «not found» (a store that is down is not a
    store that is empty)."""
    return error_code(exc) in NOT_FOUND_CODES


def ensure_bucket(client: Any, bucket: str) -> None:
    """HeadBucket, and CreateBucket when the answer is «no such bucket»;
    ``BucketAlreadyOwnedByYou`` (a lost race) is success."""
    try:
        client.head_bucket(Bucket=bucket)
        return
    except Exception as exc:  # noqa: BLE001 — re-raised unless «not found»
        if not is_not_found(exc):
            raise
    kwargs: Dict[str, Any] = {"Bucket": bucket}
    region = getattr(getattr(client, "meta", None), "region_name", None)
    if region and region != DEFAULT_REGION:
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        client.create_bucket(**kwargs)
    except Exception as exc:  # noqa: BLE001
        if error_code(exc) != "BucketAlreadyOwnedByYou":
            raise


@dataclass
class S3Config:
    """Connection config. Defaults target a LOCAL S3-compatible store (Heriverse
    convention). Credentials default to ``None``.

    :meth:`from_env` reads the SAME ``S3_*`` environment variables Heriverse-Server
    uses, so EMStudio / EMTools and Heriverse share ONE object store (same
    endpoint / bucket / prefix / keys). ``prefix`` namespaces objects
    (``<prefix>/<id>/<file>``) exactly like Heriverse's ``S3_PREFIX``."""

    endpoint: str = "localhost:9000"
    bucket: str = "em-resources"
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    secure: bool = False  # path-style http for local dev; True (https) for cloud
    prefix: str = ""      # object-key namespace (Heriverse S3_PREFIX)
    region: Optional[str] = None   # None → us-east-1 (what S3-compatible servers accept)
    force_path_style: bool = True  # custom (non-AWS) endpoints are path-style

    def to_dict(self) -> Dict[str, Any]:
        # never serialise the secret; the manifest is not a credential store
        return {"endpoint": self.endpoint, "bucket": self.bucket,
                "secure": self.secure, "prefix": self.prefix,
                "region": self.region, "force_path_style": self.force_path_style}

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "S3Config":
        """Build from the Heriverse-aligned ``S3_*`` env vars (``S3_ENDPOINT``,
        ``S3_BUCKET``, ``S3_PREFIX``, ``S3_FORCE_PATH_STYLE``, ``S3_ACCESS_KEY_ID``,
        ``S3_SECRET_ACCESS_KEY``, ``S3_REGION``). ``S3_ENDPOINT`` may include a
        scheme (``http://`` → insecure, ``https://`` → secure); defaults follow
        Heriverse's convention (``localhost:9000``, bucket ``heriverse``,
        path-style) so all tools read/write the SAME object store."""
        import os as _os
        env = env if env is not None else _os.environ
        raw = (env.get("S3_ENDPOINT") or "localhost:9000").strip()
        secure = False
        if raw.lower().startswith("https://"):
            secure, raw = True, raw[len("https://"):]
        elif raw.lower().startswith("http://"):
            secure, raw = False, raw[len("http://"):]
        endpoint = raw.rstrip("/") or "localhost:9000"
        fps = (env.get("S3_FORCE_PATH_STYLE") or "true").strip().lower()
        return cls(
            endpoint=endpoint,
            bucket=env.get("S3_BUCKET") or "heriverse",
            access_key=env.get("S3_ACCESS_KEY_ID") or None,
            secret_key=env.get("S3_SECRET_ACCESS_KEY") or None,
            secure=secure,
            prefix=(env.get("S3_PREFIX") or "").strip("/"),
            region=env.get("S3_REGION") or None,
            force_path_style=fps not in ("false", "0", "no"),
        )


@dataclass
class S3Entry:
    """One ingested object: its stable id ↔ object key + minimal metadata."""

    resource_id: str
    object_key: str
    name: str
    resource_type: str
    size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.resource_id, "object_key": self.object_key,
                "name": self.name, "resource_type": self.resource_type,
                "size": self.size}


class S3Backend(ResourceBackend):
    """An S3 object-storage backend (any S3-compatible endpoint). Same interface + stable-ID space as
    :class:`~s3dgraphy.resources.fs_backend.FSIndexBackend`; the manifest maps the
    stable id to an object key (``<id>/<filename>``) in the bucket."""

    name = "s3"

    def __init__(self, config: Optional[S3Config] = None, *,
                 client: Any = None,
                 id_factory: Optional[Callable[[], str]] = None):
        # ``client`` may be injected (tests / a pre-built client); otherwise it is
        # created lazily on first use so construction pulls in no S3 dep.
        self.config = config or S3Config()
        self._client = client
        self._entries: Dict[str, S3Entry] = {}      # resource_id -> entry
        self._by_source: Dict[str, str] = {}        # source abspath -> id (idempotent)
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    # ── client ──────────────────────────────────────────────────────────────────
    def _get_client(self):
        if self._client is None:
            try:
                self._client = make_client(self.config)
            except ImportError as exc:  # optional extra not installed
                from ..api import MissingDependency
                raise MissingDependency(
                    "the S3 backend needs the 'boto3' SDK — install s3dgraphy[s3] "
                    f"({exc})") from exc
        return self._client

    def _ensure_bucket(self, client) -> None:
        ensure_bucket(client, self.config.bucket)

    # ── ingest ────────────────────────────────────────────────────────────────────
    def ingest(self, path: str, *, resource_id: Optional[str] = None,
               object_key: Optional[str] = None) -> Tuple[str, str]:
        """Upload ``path`` into the bucket, assign/reuse a stable ID, record it,
        and return ``(stable_id, object_key)``.

        Idempotent by source path within a session (re-ingesting the same file
        reuses its stable ID). The object key defaults to ``<stable_id>/<filename>``
        so keys are unique and id-legible. Raises
        :class:`s3dgraphy.api.MissingDependency` if the SDK is absent."""
        client = self._get_client()
        self._ensure_bucket(client)
        src = os.path.abspath(path)
        rid = resource_id or self._by_source.get(src) or self._id_factory()
        base = os.path.basename(path)
        # <prefix>/<id>/<filename> — the prefix namespaces objects the same way
        # Heriverse's S3_PREFIX does, so all tools share one keyspace.
        key = object_key or "/".join(p for p in (self.config.prefix, rid, base) if p)
        client.upload_file(path, self.config.bucket, key)
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self._entries[rid] = S3Entry(
            resource_id=rid, object_key=key, name=os.path.splitext(base)[0],
            resource_type=classify_resource_type(base), size=size)
        self._by_source[src] = rid
        return rid, key

    # ── resolve (no network) ──────────────────────────────────────────────────────
    def resolve(self, resource_id: str, locator: str,
                *, graph: Any = None) -> Optional[Location]:
        """Resolve an ID this backend owns → an ``s3_uri`` Location (no network
        I/O); ``None`` (fall through) for unknown IDs. ``exists`` is ``None``
        (remote — unknown without a HEAD). Use :meth:`presign` for a fetchable
        URL."""
        entry = self._entries.get(resource_id)
        if entry is None:
            return None
        return Location(kind="s3_uri",
                        value=f"s3://{self.config.bucket}/{entry.object_key}",
                        exists=None)

    # ── presign (explicit network) ─────────────────────────────────────────────────
    def presign(self, resource_id: str, *, expires_seconds: int = 3600
                ) -> Optional[Location]:
        """Return a short-lived, fetchable ``http_url`` Location via a presigned
        GET. This DOES touch the S3 client (unlike :meth:`resolve`). ``None`` for
        unknown IDs."""
        entry = self._entries.get(resource_id)
        if entry is None:
            return None
        return self.presign_key(entry.object_key, expires_seconds=expires_seconds)

    def presign_key(self, object_key: str, *, expires_seconds: int = 3600
                    ) -> Location:
        """Presign an object key directly (stateless — no manifest lookup), for
        callers that already hold the key from :meth:`ingest` (e.g. em-bridge
        across HTTP requests). Returns an ``http_url`` Location. The URL is
        path-style (``<endpoint>/<bucket>/<key>?X-Amz-…``), signed locally (no
        request is sent) and valid for ``expires_seconds``."""
        client = self._get_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.config.bucket, "Key": object_key},
            ExpiresIn=int(expires_seconds))
        return Location(kind="http_url", value=url, exists=None)

    # ── manifest access (parallel to R1) ───────────────────────────────────────────
    def entries(self) -> List[S3Entry]:
        return sorted(self._entries.values(), key=lambda e: e.object_key)

    def to_manifest(self) -> Dict[str, Any]:
        """Serialize the id↔object-key index (no credentials)."""
        return {"config": self.config.to_dict(),
                "entries": [e.to_dict() for e in self.entries()]}

    @classmethod
    def from_manifest(cls, data: Dict[str, Any], *, client: Any = None,
                      access_key: Optional[str] = None,
                      secret_key: Optional[str] = None) -> "S3Backend":
        """Rebuild a backend from a persisted :meth:`to_manifest` record. Stable
        IDs survive; credentials are supplied fresh (never persisted)."""
        cfg_d = data.get("config", {}) or {}
        cfg = S3Config(
            endpoint=cfg_d.get("endpoint", "localhost:9000"),
            bucket=cfg_d.get("bucket", "em-resources"),
            access_key=access_key, secret_key=secret_key,
            secure=cfg_d.get("secure", False),
            prefix=cfg_d.get("prefix", ""),
            region=cfg_d.get("region"),
            force_path_style=cfg_d.get("force_path_style", True))
        be = cls(cfg, client=client)
        for d in data.get("entries", []):
            be._entries[d["id"]] = S3Entry(
                resource_id=d["id"], object_key=d["object_key"],
                name=d.get("name", ""), resource_type=d.get("resource_type", "unknown"),
                size=d.get("size", 0))
        return be
