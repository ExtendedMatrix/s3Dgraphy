"""The datamodel's fingerprint: one digest, stable under form, moved by meaning.

Every copy of the datamodel (EMStudio's vendored assets, stratigraph-templates'
snapshot, a compiled sheet's header) is compared with it, and at least one of
those comparisons runs in JavaScript. So what is defended here is:

* reordering keys or re-indenting a file does NOT move the digest;
* changing a value DOES, in any file of the set;
* the canonical form is RFC 8785, number for number — the form a JavaScript
  reader produces with ``JSON.stringify`` over sorted keys.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from s3dgraphy import api                                              # noqa: E402
from s3dgraphy.datamodel import (                                      # noqa: E402
    DATAMODEL_FILES, JSON_CONFIG, canonical_json, datamodel_fingerprint,
    fingerprint_differences)


@pytest.fixture
def copies(tmp_path):
    for filename, _ in DATAMODEL_FILES.values():
        shutil.copy(JSON_CONFIG / filename, tmp_path / filename)
    return tmp_path


def rewrite(path: pathlib.Path, change) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(change(doc), indent=3, ensure_ascii=True), encoding="utf-8")


def test_the_shape_and_the_versions_are_read_from_the_files():
    fp = datamodel_fingerprint()
    assert fp["digest"].startswith("sha256:") and len(fp["digest"]) == 7 + 64
    assert set(fp["versions"]) == set(DATAMODEL_FILES) == set(fp["digests"])
    nodes = json.loads((JSON_CONFIG / "s3Dgraphy_node_datamodel.json").read_text(encoding="utf-8"))
    assert fp["versions"]["nodes"] == nodes["s3Dgraphy_data_model_version"]
    qualia = json.loads((JSON_CONFIG / "em_qualia_types.json").read_text(encoding="utf-8"))
    assert fp["versions"]["qualia"] == qualia["metadata"]["version"]


def test_the_api_answers_the_same_question():
    assert api.datamodel_fingerprint() == datamodel_fingerprint()


def test_copies_of_the_source_have_the_source_fingerprint(copies):
    assert datamodel_fingerprint(str(copies)) == datamodel_fingerprint()


def test_reordering_keys_and_reindenting_do_not_move_it(copies):
    before = datamodel_fingerprint(str(copies))
    for filename, _ in DATAMODEL_FILES.values():
        rewrite(copies / filename, lambda d: dict(reversed(list(d.items()))))
    assert datamodel_fingerprint(str(copies)) == before


@pytest.mark.parametrize("name", sorted(DATAMODEL_FILES))
def test_changing_a_value_moves_it_and_names_the_datamodel(copies, name):
    before = datamodel_fingerprint(str(copies))
    filename = DATAMODEL_FILES[name][0]

    def touch(doc):
        doc["_a_value_that_was_not_there"] = 1
        return doc

    rewrite(copies / filename, touch)
    after = datamodel_fingerprint(str(copies))
    assert after["digest"] != before["digest"]
    assert [n for n in DATAMODEL_FILES if after["digests"][n] != before["digests"][n]] == [name]
    assert fingerprint_differences(before, after) == [
        f"{name} {before['versions'][name]}: same version, different content"]


def test_a_version_difference_is_said_copy_first():
    source = {"versions": {"nodes": "1.6.17", "connections": "1.6.31"}}
    copy = {"versions": {"nodes": "1.6.12", "connections": "1.6.31"}}
    assert fingerprint_differences(source, copy) == ["nodes 1.6.12 vs 1.6.17"]
    assert fingerprint_differences(source, {"versions": {"connections": "1.6.31"}}) == [
        "nodes: absent in the copy (1.6.17 in the source)"]
    assert fingerprint_differences(dict(source, digest="sha256:a"), dict(source)) == [
        "the copy carries no digest (compiled before the fingerprint existed)"]
    assert fingerprint_differences(source, source) == []


# ── the canonical form is RFC 8785 ───────────────────────────────────────────

@pytest.mark.parametrize("value, written", [
    (1.0, "1"),                      # 139 of these in em_visual_rules.json
    (0.0, "0"), (-0.0, "0"),
    (1e-5, "0.00001"), (1e-7, "1e-7"),
    (1e21, "1e+21"), (1e20, "100000000000000000000"),
    (123.456, "123.456"), (-0.5, "-0.5"),
    (5e-324, "5e-324"), (1.7976931348623157e308, "1.7976931348623157e+308"),
    (333333333.3333333, "333333333.3333333"),
    (7, "7"), (True, "true"), (None, "null"),
])
def test_numbers_are_written_as_ecmascript_writes_them(value, written):
    assert canonical_json(value) == written.encode()


def test_keys_sort_by_utf16_and_strings_escape_as_json_stringify():
    # U+FB01 (BMP) sorts AFTER U+1F600 (astral) in UTF-16, before it in code points
    doc = {"ﬁ": 1, "\U0001f600": 2, "b": "é\n \x01\"", "a": [1.5, {}]}
    assert canonical_json(doc) == (
        '{"a":[1.5,{}],"b":"é\\n \\u0001\\"","\U0001f600":2,"ﬁ":1}'
    ).encode("utf-8")


def test_a_partial_set_has_no_fingerprint(copies):
    (copies / DATAMODEL_FILES["translations"][0]).unlink()
    with pytest.raises(FileNotFoundError):
        datamodel_fingerprint(str(copies))


# ── one digest per file, and the files a consumer reads (dev25) ──────────────

READS = ("nodes", "node_registry", "connections", "qualia")   # stratigraph-templates


def test_files_carries_a_digest_and_a_version_per_file():
    fp = datamodel_fingerprint()
    assert list(fp["files"]) == list(DATAMODEL_FILES)
    for name, (filename, _) in DATAMODEL_FILES.items():
        entry = fp["files"][name]
        assert entry == {"file": filename, "digest": fp["digests"][name],
                         "version": fp["versions"][name]}
        canon = canonical_json(json.loads((JSON_CONFIG / filename).read_text(encoding="utf-8")))
        import hashlib
        assert entry["digest"] == "sha256:" + hashlib.sha256(canon).hexdigest()


def test_a_subset_has_no_one_digest_and_the_whole_set_keeps_it():
    from s3dgraphy.datamodel import fingerprint_subset
    fp = datamodel_fingerprint()
    sub = fingerprint_subset(fp, READS)
    assert "digest" not in sub
    assert list(sub["versions"]) == list(sub["digests"]) == list(sub["files"]) == list(READS)
    assert fingerprint_subset(fp)["digest"] == fp["digest"]
    assert api.datamodel_fingerprint_subset(fp, READS) == sub


@pytest.mark.parametrize("name", ["visual_rules", "translations"])
def test_a_file_a_consumer_does_not_read_is_not_its_difference(copies, name):
    before = datamodel_fingerprint(str(copies))
    rewrite(copies / DATAMODEL_FILES[name][0], lambda d: dict(d, _touched=1))
    after = datamodel_fingerprint(str(copies))
    assert after["digest"] != before["digest"]
    assert fingerprint_differences(before, after, READS) == []
    assert api.datamodel_differences(before, after, READS) == []
    # the whole set still sees it
    assert fingerprint_differences(before, after) != []


def test_a_file_it_reads_is_named():
    fp = datamodel_fingerprint()
    old = dict(fp, versions=dict(fp["versions"], nodes="1.6.17"))
    assert fingerprint_differences(fp, old, READS) == [
        f"nodes 1.6.17 vs {fp['versions']['nodes']}"]


def test_a_fingerprint_from_before_dev25_still_compares():
    fp = datamodel_fingerprint()
    old = dict(fp, files={n: spec[0] for n, spec in DATAMODEL_FILES.items()})
    assert fingerprint_differences(fp, old) == []
    assert fingerprint_differences(fp, old, READS) == []
