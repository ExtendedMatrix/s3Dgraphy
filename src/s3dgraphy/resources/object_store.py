"""The object store the Resource layer keeps its bucket in — any S3-compatible one.

RustFS today, tomorrow another (Ceph, Garage, SeaweedFS, AWS S3, a cloud
provider's): what the rest of s3Dgraphy needs from a bucket is five small things,
and nothing here names a vendor.

* ``locator(key)`` / ``key_of(locator)`` — the ``s3://bucket/key`` address of an
  object, and back (``None`` for an address that is not this store's);
* ``stat(key)`` — does it exist, and how big;
* ``sha256(key)`` — the digest of the bytes, read by streaming (the only proof
  that two copies are the same bytes: an ETag is a digest of the PARTS of a
  multipart upload, not of the file);
* ``put(path, key)`` and ``delete(key)``;
* ``listing(prefix, …)`` — what is in it, one level (folders = common
  prefixes) a page at a time, or a search by name under a prefix
  (MICRO-F-BUCKET-E-TILESET p.1: Archive ▸ Files ▸ Bucket).

:class:`S3Store` implements them over the S3 API through ``boto3`` — plain S3
operations (HeadBucket, CreateBucket, HeadObject, GetObject, PutObject,
DeleteObject), path-style, which any S3-compatible endpoint speaks. A store that
needs another client (a provider's SDK) is one more class with the same
five methods, registered with :func:`register_store`; the connection is read
from the ``S3_*`` environment (the SAME variables Heriverse-Server uses), and
``EM_OBJECT_STORE`` names which implementation opens it (default ``s3``).

The SDK is imported lazily: without it, ``import s3dgraphy`` still works and the
store raises :class:`StoreUnavailable` when first used.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable, Dict, Optional

from .s3_backend import S3Config, ensure_bucket, is_not_found, make_client


class StoreError(RuntimeError):
    """The store answered with an error (not «no such object»)."""


class StoreUnavailable(StoreError):
    """The SDK is not installed, or the store cannot be reached at all."""


class ObjectStore:
    """The five operations the Resource layer needs from a bucket."""

    name = "abstract"

    def locator(self, key: str) -> str:
        raise NotImplementedError

    def key_of(self, locator: str) -> Optional[str]:
        raise NotImplementedError

    def key_for(self, resource_id: str, filename: str) -> str:
        """The key a resource's file is kept under: ``<prefix>/<id>/<filename>``
        (the same layout ``S3Backend.ingest`` writes and Heriverse reads)."""
        raise NotImplementedError

    def stat(self, key: str) -> Optional[Dict[str, Any]]:
        """``{size, etag}`` of the object, or ``None`` when it is not there."""
        raise NotImplementedError

    def sha256(self, key: str) -> str:
        """The hex sha256 of the object's bytes, by streaming."""
        raise NotImplementedError

    def put(self, path: str, key: str) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def listing(self, prefix: str = "", *, token: Optional[str] = None, limit: int = 1000,
                search: str = "", scan_max: int = 20000) -> Dict[str, Any]:
        """What the bucket holds under ``prefix``: ``{folders: [prefix/], objects:
        [{key, size, modified, etag}], next_token, truncated, scanned}``. One
        level (the folders are the common prefixes), ``limit`` objects a page,
        ``token`` the next page. With ``search`` the whole tree under ``prefix``
        is read (up to ``scan_max`` keys) and only the names that contain it
        come back, no folders."""
        raise NotImplementedError


class S3Store(ObjectStore):
    """Any S3-compatible endpoint, through a ``boto3`` S3 client (or an injected
    client with the same ``head_object`` / ``get_object`` / ``upload_file`` /
    ``delete_object`` / ``head_bucket`` / ``create_bucket`` methods)."""

    name = "s3"

    def __init__(self, config: Optional[S3Config] = None, client: Any = None):
        self.config = config or S3Config.from_env()
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                self._client = make_client(self.config)
            except ImportError as exc:
                raise StoreUnavailable(
                    "the object store needs the 'boto3' SDK (it speaks to any "
                    f"S3-compatible server): pip install s3dgraphy[s3] ({exc})") from exc
        return self._client

    def locator(self, key: str) -> str:
        return f"s3://{self.config.bucket}/{key}"

    def key_of(self, locator: str) -> Optional[str]:
        text = str(locator or "").strip()
        prefix = f"s3://{self.config.bucket}/"
        return text[len(prefix):] if text.lower().startswith(prefix.lower()) else None

    def key_for(self, resource_id: str, filename: str) -> str:
        return "/".join(p for p in (self.config.prefix, resource_id, filename) if p)

    def stat(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            head = self._get_client().head_object(Bucket=self.config.bucket, Key=key)
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001 — botocore's ClientError & co.
            if is_not_found(exc):
                return None
            raise StoreError(f"{self.locator(key)}: {exc}") from exc
        return {"size": int(head.get("ContentLength") or 0),
                "etag": str(head.get("ETag") or "").strip('"')}

    def sha256(self, key: str) -> str:
        client = self._get_client()
        try:
            body = client.get_object(Bucket=self.config.bucket, Key=key)["Body"]
        except Exception as exc:  # noqa: BLE001
            raise StoreError(f"{self.locator(key)}: {exc}") from exc
        h = hashlib.sha256()
        try:
            for chunk in iter(lambda: body.read(1 << 20), b""):
                h.update(chunk)
        finally:
            body.close()      # a stream left open is a connection the pool loses
        return h.hexdigest()

    def put(self, path: str, key: str) -> None:
        client = self._get_client()
        try:
            ensure_bucket(client, self.config.bucket)
            client.upload_file(path, self.config.bucket, key)
        except Exception as exc:  # noqa: BLE001
            raise StoreError(f"{self.locator(key)}: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._get_client().delete_object(Bucket=self.config.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StoreError(f"{self.locator(key)}: {exc}") from exc

    def listing(self, prefix: str = "", *, token: Optional[str] = None, limit: int = 1000,
                search: str = "", scan_max: int = 20000) -> Dict[str, Any]:
        client = self._get_client()
        prefix = str(prefix or "").lstrip("/")
        limit = max(1, min(int(limit or 1000), 1000))      # S3's own page

        def page(**kw):
            try:
                return client.list_objects_v2(Bucket=self.config.bucket, Prefix=prefix, **kw)
            except Exception as exc:  # noqa: BLE001
                if is_not_found(exc):
                    raise StoreError(f"s3://{self.config.bucket}: no such bucket") from exc
                raise StoreError(f"s3://{self.config.bucket}/{prefix}: {exc}") from exc

        def obj(o):
            m = o.get("LastModified")
            return {"key": o["Key"], "size": int(o.get("Size") or 0),
                    "modified": m.isoformat() if hasattr(m, "isoformat") else (str(m) if m else None),
                    "etag": str(o.get("ETag") or "").strip('"')}

        if search:
            want = str(search).lower()
            found, scanned, tok, truncated = [], 0, token, False
            while True:
                r = page(MaxKeys=1000, **({"ContinuationToken": tok} if tok else {}))
                for o in r.get("Contents") or []:
                    scanned += 1
                    if want in o["Key"].rsplit("/", 1)[-1].lower():
                        found.append(obj(o))
                tok = r.get("NextContinuationToken")
                if not r.get("IsTruncated") or not tok:
                    break
                if scanned >= scan_max or len(found) >= limit:
                    truncated = True
                    break
            return {"folders": [], "objects": found[:limit], "next_token": tok if truncated else None,
                    "truncated": truncated, "scanned": scanned}
        r = page(Delimiter="/", MaxKeys=limit, **({"ContinuationToken": token} if token else {}))
        return {"folders": [c["Prefix"] for c in r.get("CommonPrefixes") or []],
                "objects": [obj(o) for o in r.get("Contents") or [] if o["Key"] != prefix],
                "next_token": r.get("NextContinuationToken") if r.get("IsTruncated") else None,
                "truncated": bool(r.get("IsTruncated")), "scanned": int(r.get("KeyCount") or 0)}


_FACTORIES: Dict[str, Callable[[Optional[S3Config]], ObjectStore]] = {
    "s3": lambda cfg: S3Store(cfg),
}


def register_store(name: str, factory: Callable[[Optional[S3Config]], ObjectStore]) -> None:
    """Plug in another implementation: ``factory(config) -> ObjectStore``."""
    _FACTORIES[str(name).lower()] = factory


def open_store(name: Optional[str] = None, config: Optional[S3Config] = None) -> ObjectStore:
    """The store the environment names (``EM_OBJECT_STORE``, default ``s3``),
    connected as the ``S3_*`` variables say."""
    chosen = str(name or os.environ.get("EM_OBJECT_STORE") or "s3").lower()
    if chosen not in _FACTORIES:
        raise StoreUnavailable(f"no object store called {chosen!r}: {sorted(_FACTORIES)}")
    return _FACTORIES[chosen](config)
