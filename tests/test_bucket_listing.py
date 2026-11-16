"""MICRO-F-BUCKET-E-TILESET p.1 · what a bucket holds, as Archive ▸ Files ▸
Bucket reads it: one level (folders = common prefixes), a page at a time, a
search by name. moto stands for any S3-compatible server (RustFS, MinIO, S3)."""
import pytest

moto = pytest.importorskip("moto")
boto3 = pytest.importorskip("boto3")

from s3dgraphy.resources.object_store import S3Store, StoreError
from s3dgraphy.resources.s3_backend import S3Config


@pytest.fixture
def store():
    with moto.mock_aws():
        c = boto3.client("s3", region_name="us-east-1")
        c.create_bucket(Bucket="em-assets")
        for i in range(250):
            c.put_object(Bucket="em-assets", Key=f"rilievi/2015/foto_{i:03d}.jpg", Body=b"x" * i)
        c.put_object(Bucket="em-assets", Key="rilievi/Survey_2015.3tz", Body=b"tz")
        c.put_object(Bucket="em-assets", Key="catasto/foglio_01.tif", Body=b"tif")
        c.put_object(Bucket="em-assets", Key="leggimi.txt", Body=b"t")
        yield S3Store(S3Config(bucket="em-assets"), client=c)


def test_one_level_folders_and_files(store):
    top = store.listing("")
    assert top["folders"] == ["catasto/", "rilievi/"]
    assert [o["key"] for o in top["objects"]] == ["leggimi.txt"]
    r = store.listing("rilievi/")
    assert r["folders"] == ["rilievi/2015/"] and [o["key"] for o in r["objects"]] == ["rilievi/Survey_2015.3tz"]
    o = r["objects"][0]
    assert o["size"] == 2 and o["modified"] and not r["truncated"]


def test_pages_with_a_token(store):
    seen, tok, pages = [], None, 0
    while True:
        r = store.listing("rilievi/2015/", token=tok, limit=100)
        seen += [o["key"] for o in r["objects"]]
        pages += 1
        tok = r["next_token"]
        if not tok:
            break
    assert pages == 3 and len(seen) == 250 == len(set(seen))


def test_search_by_name_under_a_prefix(store):
    r = store.listing("", search="SURVEY")
    assert [o["key"] for o in r["objects"]] == ["rilievi/Survey_2015.3tz"] and r["folders"] == []
    assert r["scanned"] == 253
    assert len(store.listing("rilievi/", search="foto_1")["objects"]) == 100   # foto_100…foto_199


def test_a_bucket_that_is_not_there_is_said(store):
    other = S3Store(S3Config(bucket="nessuno"), client=store._client)
    with pytest.raises(StoreError, match="no such bucket"):
        other.listing("")
