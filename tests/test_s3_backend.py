"""R2 — the S3 resource backend (object-storage tier, boto3).

Verifies (R2 DoD): ingest → object_key + stable ID + manifest entry; resolve →
s3_uri Location (no network); presign → http_url Location; registers above
passthrough (same interface + stable-ID space as R1); MissingDependency when the
SDK is absent. The S3 client is MOCKED — no running S3 server required.
"""

import sys

import pytest

from s3dgraphy import api
from s3dgraphy.resources import (
    S3Backend,
    S3Config,
    default_registry,
)


class _NotFound(Exception):
    """What botocore's ClientError carries for a HEAD on a missing bucket."""
    response = {"Error": {"Code": "404"}}


class _FakeS3Client:
    """A stand-in for a boto3 S3 client — records calls, needs no server."""

    def __init__(self):
        self.buckets = set()
        self.put = []            # (bucket, key, path)
        self.presigned = []      # (bucket, key)
        self.expires = []        # ExpiresIn of each presign

    def head_bucket(self, Bucket):
        if Bucket not in self.buckets:
            raise _NotFound()

    def create_bucket(self, Bucket, **kwargs):
        self.buckets.add(Bucket)

    def upload_file(self, Filename, Bucket, Key):
        self.put.append((Bucket, Key, Filename))

    def generate_presigned_url(self, ClientMethod, Params=None, ExpiresIn=3600):
        assert ClientMethod == "get_object"
        bucket, key = Params["Bucket"], Params["Key"]
        self.presigned.append((bucket, key))
        self.expires.append(ExpiresIn)
        return f"http://localhost:9000/{bucket}/{key}?X-Amz-Signature=deadbeef"


def _mk(tmp_path, name="scan.obj", content="x"):
    f = tmp_path / name
    f.write_text(content)
    return str(f)


# ── ingest ────────────────────────────────────────────────────────────────────
def test_ingest_uploads_and_records_stable_id(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="em-resources"), client=client)
    path = _mk(tmp_path, "site.obj")
    rid, key = be.ingest(path)
    assert rid and key == f"{rid}/site.obj"          # id-legible object key
    assert client.buckets == {"em-resources"}         # bucket auto-created
    assert client.put == [("em-resources", key, path)]  # object uploaded
    entry = be.entries()[0]
    assert entry.resource_id == rid and entry.object_key == key
    assert entry.resource_type == "3d_model"          # classified via ResourceNode vocab


def test_ingest_is_idempotent_by_source_path(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(client=client)
    path = _mk(tmp_path, "a.pdf")
    rid1, _ = be.ingest(path)
    rid2, _ = be.ingest(path)     # same file again → same stable ID
    assert rid1 == rid2 and len(be.entries()) == 1


def test_ingest_honours_explicit_id(tmp_path):
    be = S3Backend(client=_FakeS3Client())
    rid, key = be.ingest(_mk(tmp_path), resource_id="fixed-id")
    assert rid == "fixed-id" and key.startswith("fixed-id/")


# ── resolve (no network) ───────────────────────────────────────────────────────
def test_resolve_returns_s3_uri_without_network(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="assets"), client=client)
    rid, key = be.ingest(_mk(tmp_path, "m.glb"))
    loc = be.resolve(rid, "")
    assert loc.kind == "s3_uri" and loc.value == f"s3://assets/{key}"
    assert loc.exists is None                 # remote — unknown without a HEAD
    assert client.presigned == []             # resolve did NOT touch the network


def test_resolve_unknown_id_falls_through():
    be = S3Backend(client=_FakeS3Client())
    assert be.resolve("no-such-id", "") is None


# ── presign (explicit network) ─────────────────────────────────────────────────
def test_presign_returns_http_url(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="assets"), client=client)
    rid, key = be.ingest(_mk(tmp_path, "photo.jpg"))
    loc = be.presign(rid, expires_seconds=120)
    assert loc.kind == "http_url" and loc.value.startswith("http://localhost:9000/assets/")
    assert client.presigned == [("assets", key)]   # presign DID call the client
    assert client.expires == [120]                 # the expiry reaches boto3


# ── registry integration (same interface + stable-ID space as R1) ──────────────
def test_registers_above_passthrough(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="assets"), client=client)
    rid, key = be.ingest(_mk(tmp_path, "x.obj"))

    reg = default_registry()             # passthrough only
    reg.register(be, priority=20)        # S3 on top
    assert [b.name for b in reg.backends()] == ["s3", "passthrough"]

    owned = reg.resolve(rid, "ignored-locator")
    assert owned.kind == "s3_uri" and owned.value == f"s3://assets/{key}"
    # a url-only resource the S3 backend doesn't own → passthrough
    other = reg.resolve("some-linknode-uuid", "https://zenodo.org/record/1")
    assert other.kind == "http_url" and other.value == "https://zenodo.org/record/1"


# ── manifest round-trip (parallel to R1) ────────────────────────────────────────
def test_manifest_roundtrip_preserves_ids(tmp_path):
    be = S3Backend(S3Config(bucket="assets"), client=_FakeS3Client())
    rid, key = be.ingest(_mk(tmp_path, "y.obj"))
    manifest = be.to_manifest()
    assert "access_key" not in str(manifest)   # credentials never serialised
    rebuilt = S3Backend.from_manifest(manifest, client=_FakeS3Client())
    assert rebuilt.resolve(rid, "").value == f"s3://assets/{key}"
    assert rebuilt.config.bucket == "assets"


# ── optional dependency → MissingDependency ─────────────────────────────────────
def test_missing_sdk_raises_missing_dependency(tmp_path, monkeypatch):
    # Simulate the 'boto3' SDK being absent: `import boto3` → ImportError.
    monkeypatch.setitem(sys.modules, "boto3", None)
    be = S3Backend()  # no injected client → will try to import the SDK
    with pytest.raises(api.MissingDependency):
        be.ingest(_mk(tmp_path))


def test_missing_dependency_is_importerror():
    # transports map it to a 501 (same contract as rdflib for TTL)
    assert issubclass(api.MissingDependency, ImportError)


# ── shared config from Heriverse S3_* env (connective tissue) ──────────────────
def test_config_from_env_aligns_to_heriverse():
    env = {
        "S3_ENDPOINT": "http://localhost:9000",
        "S3_BUCKET": "heriverse",
        "S3_PREFIX": "heriverse",
        "S3_FORCE_PATH_STYLE": "true",
        "S3_ACCESS_KEY_ID": "admin",
        "S3_SECRET_ACCESS_KEY": "password",
        "S3_REGION": "eu-west-1",
    }
    c = S3Config.from_env(env)
    assert c.endpoint == "localhost:9000" and c.secure is False   # scheme stripped
    assert c.bucket == "heriverse" and c.prefix == "heriverse"
    assert c.access_key == "admin" and c.secret_key == "password"
    assert c.region == "eu-west-1" and c.force_path_style is True


def test_config_from_env_https_is_secure():
    c = S3Config.from_env({"S3_ENDPOINT": "https://s3.example.org"})
    assert c.endpoint == "s3.example.org" and c.secure is True


def test_config_from_env_defaults_to_heriverse_convention():
    c = S3Config.from_env({})   # nothing set → shared defaults
    assert c.endpoint == "localhost:9000" and c.bucket == "heriverse"
    assert c.force_path_style is True


def test_prefix_namespaces_object_key(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="heriverse", prefix="heriverse"), client=client)
    rid, key = be.ingest(_mk(tmp_path, "m.glb"))
    assert key == f"heriverse/{rid}/m.glb"
    assert be.resolve(rid, "").value == f"s3://heriverse/heriverse/{rid}/m.glb"


def test_presign_key_is_stateless(tmp_path):
    client = _FakeS3Client()
    be = S3Backend(S3Config(bucket="assets"), client=client)
    loc = be.presign_key("some/known/key.obj", expires_seconds=60)
    assert loc.kind == "http_url"
    assert client.presigned == [("assets", "some/known/key.obj")]


# ── api op forwards resource_id (promote keeps the stable ID) ──────────────────
def test_api_ingest_forwards_resource_id(monkeypatch):
    import s3dgraphy.resources as R
    seen = {}

    class _FakeBackend:
        def __init__(self, cfg):
            self.cfg = cfg

        def ingest(self, path, *, resource_id=None, object_key=None):
            seen["resource_id"] = resource_id
            return (resource_id or "minted", f"{resource_id}/x.obj")

    monkeypatch.setattr(R, "S3Backend", _FakeBackend)
    out = api.ingest_s3_resource("/local/x.obj", resource_id="keep-me",
                                 config=S3Config(bucket="b"))
    # the existing stable ID is preserved end-to-end (one ID space FS↔S3)
    assert seen["resource_id"] == "keep-me"
    assert out["id"] == "keep-me" and out["s3_uri"] == "s3://b/keep-me/x.obj"


# ── the seam stays S3-dep-free ──────────────────────────────────────────────────
def test_construction_pulls_no_s3_dep(monkeypatch):
    # Force `import boto3` to fail; constructing the backend (and any dep-free
    # op) must still work — the SDK is only touched on a network op.
    monkeypatch.setitem(sys.modules, "boto3", None)
    from s3dgraphy.resources import S3Backend, S3Config
    be = S3Backend(S3Config())
    assert be.name == "s3"
    assert be.resolve("unknown", "") is None   # dep-free lookup still works
