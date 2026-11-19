"""MICRO-PL21 · the index of a repository (row X1).

``python -m s3dgraphy.extensions server-generate --repo-dir D`` lists every
archive of D in ``D/index.json``, in the form of Blender's Extension Listing
API v1, with our ``sections``, ``requires``, ``content_hash`` and
``reviewed``. The archives are the SYNTHETIC ones of tests/data/profiles
(D-5, marked ESEMPIO), built with ``build``.
"""
import json
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.extensions import repository as R
from s3dgraphy.profiles.problems import MESSAGES

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
STAT = "https://w3id.org/extendedmatrix/profile/esempio-statuaria/vocab/punti-volto/"


def built(src: Path, repo: Path) -> Path:
    res = X.build(src, output_dir=repo)
    assert res["ok"], res["errors"]
    return Path(res["path"])


def set_toml(folder: Path, pattern: str, repl: str):
    p = folder / "em-extension.toml"
    text, n = re.subn(pattern, repl, p.read_text(encoding="utf-8"), count=1, flags=re.M)
    assert n, pattern
    p.write_text(text, encoding="utf-8")


def copy(src: Path, tmp_path: Path, name=None) -> Path:
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    return dst


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "repo"
    d.mkdir()
    built(SEPARATE, d)
    built(PLUGIN, d)
    return d


def codes(res, level=None):
    out = [p["code"] for p in res["problems"] if level is None or p["level"] == level]
    for x in res["listed"]:
        out += [p["code"] for p in x["warnings"] if level in (None, "warning")]
    for x in res["refused"]:
        out += [p["code"] for p in x["errors"] if level in (None, "error")]
        out += [p["code"] for p in x["warnings"] if level in (None, "warning")]
    return out


def test_the_index_has_the_form_of_blenders_listing_api(repo):
    res = X.server_generate(repo)
    assert res["ok"] and res["written"]
    doc = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    assert doc == res["index"]
    assert doc["version"] == "v1" and doc["blocklist"] == []
    assert [(e["id"], e["type"]) for e in doc["data"]] == [("esempio-statuaria", "community-package"),
                                                         ("facemesh_fit", "plugin")]
    assert X.validate_index(doc).ok
    for e in doc["data"]:
        for k in R.ENTRY_REQUIRED:
            assert e[k] not in (None, "", []), k
        blob = (repo / e["archive_url"][2:]).read_bytes()
        assert e["archive_url"] == f"./{e['id']}-{e['version']}.zip"
        assert e["archive_size"] == len(blob) and X.verify_archive(blob, e).ok
        assert "em_api_min" in e and "blender_version_min" not in e


def test_the_sections_say_versions_digests_vocabularies_and_code(repo):
    doc = X.server_generate(repo)["index"]
    stat, plug = doc["data"]
    data = stat["sections"]["data"]
    assert set(stat["sections"]) == {"data"} and data["version"] == "0.1.0"
    assert re.match(r"^sha256:[0-9a-f]{64}$", data["digest"])
    v = {x["scheme"]: x for x in data["vocabularies"]}[STAT]
    assert v["fascia"] == "A" and v["license"] == "SPDX:CC-BY-4.0" and v["digest"].startswith("sha256:")
    code = plug["sections"]["code"]
    assert set(plug["sections"]) == {"code"} and code["module"] == "facemesh_fit"
    assert code["hosts"] == ["emstudio"] and "files" in code["permissions"]
    assert plug["permissions"] == code["permissions"] and plug["platforms"] == code["platforms"]
    assert plug["requires"]["extensions"][0]["id"] == "esempio-statuaria"


def test_archive_hash_is_the_zips_and_content_hash_the_registers(repo, tmp_path):
    doc = X.server_generate(repo)["index"]
    e = doc["data"][0]
    assert e["archive_hash"] != e["content_hash"]
    X.install((repo / e["archive_url"][2:]).read_bytes())
    assert X.read_register()["extensions"][e["id"]]["archive_hash"] == e["content_hash"]


def test_the_index_is_deterministic_and_check_writes_nothing(repo):
    X.server_generate(repo)
    first = (repo / "index.json").read_bytes()
    X.server_generate(repo)
    assert (repo / "index.json").read_bytes() == first
    res = X.server_generate(repo, check=True)
    assert res["ok"] and res["same"] and not res["written"]
    (repo / "index.json").write_text("{}", encoding="utf-8")
    res = X.server_generate(repo, check=True)
    assert not res["ok"] and not res["same"] and "index_differs" in codes(res, "error")
    assert (repo / "index.json").read_text(encoding="utf-8") == "{}"


def test_base_url_html_and_versions_newest_first(repo, tmp_path):
    newer = copy(PLUGIN, tmp_path)
    set_toml(newer, r'^version = "0.2.0"', 'version = "0.10.0"')     # semver, not text: 0.10 > 0.2
    (newer / "facemesh_fit" / "__init__.py").write_text("# 0.10\n" + (PLUGIN / "facemesh_fit" / "__init__.py")
                                                         .read_text(encoding="utf-8"), encoding="utf-8")
    built(newer, repo)
    res = X.server_generate(repo, base_url="https://example.org/ext/", html_page=True)
    assert res["ok"], res
    ids = [(e["id"], e["version"]) for e in res["index"]["data"]]
    assert ids == [("esempio-statuaria", "0.1.0"), ("facemesh_fit", "0.10.0"), ("facemesh_fit", "0.2.0")]
    assert res["index"]["data"][1]["archive_url"] == "https://example.org/ext/facemesh_fit-0.10.0.zip"
    page = (repo / "index.html").read_text(encoding="utf-8")
    assert "facemesh_fit-0.10.0.zip" in page and "Pacchetto di comunità" in page and "Community package" in page


def test_a_file_url_repository_resolves_relative_archives(repo):
    X.server_generate(repo)
    url = (repo / "index.json").as_uri()
    doc = json.load(urllib.request.urlopen(url))
    for e in doc["data"]:
        blob = urllib.request.urlopen(urllib.parse.urljoin(url, e["archive_url"])).read()
        assert X.verify_archive(blob, e).ok
        bad = X.verify_archive(blob + b"\0", e)
        assert bad.codes("error") == ["index_size_mismatch", "index_hash_mismatch"]


def test_a_refused_archive_is_not_listed_and_the_command_fails(repo, tmp_path):
    (repo / "broken.zip").write_bytes(b"not a zip")
    res = X.server_generate(repo)
    assert not res["ok"] and res["written"]
    assert [x["file"] for x in res["refused"]] == ["broken.zip"]
    assert len(res["index"]["data"]) == 2


def test_a_bare_profile_or_an_entry_without_blenders_fields_is_refused(repo, tmp_path):
    import zipfile
    with zipfile.ZipFile(repo / "bare.zip", "w") as z:
        for p in sorted(SEPARATE.rglob("*")):
            if p.is_file() and p.name != "em-extension.toml":
                z.write(p, p.relative_to(SEPARATE).as_posix())
    entry, rep = R.index_entry(repo / "bare.zip", archive_url="./bare.zip")
    assert entry is None and "index_no_envelope" in rep.codes("error")
    # a bare profile built: build writes a tagline only when the first sentence fits 64 characters
    from tests.test_extensions_cli import bare
    src = bare(tmp_path)
    prof = json.loads((src / "profile.json").read_text(encoding="utf-8"))
    prof["description"] = {k: "A long description of a package whose first sentence does not fit in sixty-four characters."
                           for k in prof["description"]}
    (src / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    out = tmp_path / "o"
    out.mkdir()
    z = Path(X.build(src, output_dir=out)["path"])
    entry, rep = R.index_entry(z, archive_url="./x.zip")
    assert entry is None and rep.codes("error") == ["index_entry_fields"]
    assert "tagline" in rep.problems[-1].text("it")
    blob = next(repo.glob("facemesh_fit-*.zip")).read_bytes()
    assert R.index_entry(None, blob=blob, archive_url="./f.zip")[0] is not None


def test_blocklist_and_reviewed(repo):
    doc = X.server_generate(repo)["index"]
    plug = [e for e in doc["data"] if e["id"] == "facemesh_fit"][0]
    (repo / "reviewed.json").write_text(json.dumps({"reviewed": [
        {"id": "facemesh_fit", "digest": plug["sections"]["code"]["digest"], "by": "orcid:0000-0000-0000-0000",
         "on": "2026-11-19"},
        {"id": "esempio-statuaria", "digest": "sha256:" + "0" * 64, "by": "x", "on": "2026-11-19"}]}), encoding="utf-8")
    res = X.server_generate(repo)
    rows = {e["id"]: e for e in res["index"]["data"]}
    assert rows["facemesh_fit"]["reviewed"]["by"] == "orcid:0000-0000-0000-0000"
    assert "reviewed" not in rows["esempio-statuaria"]          # another digest: not this content
    (repo / "blocklist.json").write_text(json.dumps([{"id": "facemesh_fit", "reason": "withdrawn",
                                                      "reason_it": "ritirato"}]), encoding="utf-8")
    res = X.server_generate(repo)
    assert res["ok"] and [e["id"] for e in res["index"]["data"]] == ["esempio-statuaria"]
    assert res["index"]["blocklist"] == [{"id": "facemesh_fit", "reason": "withdrawn", "reason_it": "ritirato"}]
    assert [x for x in res["refused"] if x.get("blocked")][0]["warnings"][0]["code"] == "index_blocked"
    (repo / "blocklist.json").write_text(json.dumps([{"id": "x"}]), encoding="utf-8")
    res = X.server_generate(repo, dry_run=True)
    assert not res["ok"] and "index_block_reason" in codes(res, "error")


def test_a_section_version_reused_with_other_content_is_refused(repo, tmp_path):
    other = copy(PLUGIN, tmp_path)       # archive 0.2.1, its code still says 0.2.0 but is not the same
    set_toml(other, r'^version = "0.2.0"', 'version = "0.2.1"')
    set_toml(other, r'^\[code\]$', '[code]\nversion = "0.2.0"')
    (other / "facemesh_fit" / "__init__.py").write_text("# changed\n", encoding="utf-8")
    built(other, repo)
    res = X.server_generate(repo)
    assert not res["ok"]
    assert "index_section_reused" in codes(res, "error")
    assert "facemesh_fit-0.2.1.zip" in [x["file"] for x in res["refused"]]
    assert [e["version"] for e in res["index"]["data"] if e["id"] == "facemesh_fit"] == ["0.2.0"]


def test_the_same_id_and_version_twice_is_refused(repo):
    shutil.copy(next(repo.glob("facemesh_fit-*.zip")), repo / "copia.zip")
    res = X.server_generate(repo)
    assert "index_duplicate" in codes(res, "error") and "index_file_name" in codes(res, "warning")


def test_vocabularies_another_owns_and_shared_ones():
    def entry(eid, scheme, digest="sha256:" + "1" * 64, version="0.1.0"):
        return {"id": eid, "version": "1.0.0", "requires": {}, "where": f"{eid}.zip",
                "sections": {"data": {"version": "1.0.0", "digest": "sha256:" + eid[0] * 64,
                                      "vocabularies": [{"scheme": scheme, "version": version, "digest": digest}]}}}
    r = X.repository_checks([entry("esempio-statuaria", STAT), entry("ritratti", STAT)])
    assert r.codes("error") == ["index_vocab_owner"]                  # the owner is published here
    r = X.repository_checks([entry("ritratti", STAT)])
    assert r.codes() == ["index_vocab_not_owner"] and r.ok          # it may be published elsewhere
    r = X.repository_checks([entry("ritratti", "https://w3id.org/extendedmatrix/vocab/em-us-definizione/")])
    assert r.codes() == ["index_vocab_central"] and r.ok
    r = X.repository_checks([entry("a", "https://example.org/v/"),
                             entry("b", "https://example.org/v/", digest="sha256:" + "2" * 64)])
    assert r.codes("error") == ["index_vocab_conflict"]
    r = X.repository_checks([entry("a", "https://example.org/v/"),
                             entry("b", "https://example.org/v/", digest="sha256:" + "2" * 64, version="0.2.0")])
    assert r.ok and not r.codes()


def test_requires_cycles_only_through_mandatory_dependencies():
    def e(eid, *deps, optional=False):
        return {"id": eid, "version": "1.0.0", "sections": {},
                "requires": {"extensions": [{"id": d, "optional": optional} for d in deps]}}
    # the SPEC's own example: statuaria offers facemesh_fit (optional), which needs statuaria
    assert X.repository_checks([e("stat", "fm", optional=True), e("fm", "stat")]).ok
    r = X.repository_checks([e("a", "b"), e("b", "c"), e("c", "a")])
    assert r.codes("error") == ["index_requires_cycle"]
    assert "a → b → c → a" in r.problems[0].text("it")
    r = X.repository_checks([e("a", "altrove")])
    assert r.codes() == ["index_requires_elsewhere"] and r.ok


def test_validate_index_for_the_clients():
    assert X.validate_index([]).codes() == ["index_shape"]
    assert X.validate_index({"version": "v2", "data": []}).codes() == ["index_version"]
    r = X.validate_index({"version": "v1", "data": [{"id": "x", "version": "1.0", "archive_hash": "md5:1"}]})
    assert set(r.codes()) == {"index_entry_fields", "index_entry_hash", "version_bad"}


def test_the_command_line(repo, capsys):
    assert cli.main(["server-generate", "--repo-dir", str(repo), "--lang", "it", "--html"]) == 0
    out = capsys.readouterr().out
    assert "OK  esempio-statuaria-0.1.0.zip" in out and "2 voci" in out and (repo / "index.html").is_file()
    assert cli.main(["--lang", "it", "server-generate", "--repo-dir", str(repo), "--check"]) == 0
    assert "invariato" in capsys.readouterr().out
    (repo / "junk.zip").write_bytes(b"x")
    assert cli.main(["server-generate", "--repo-dir", str(repo), "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["refused"][0]["file"] == "junk.zip" and "index" not in doc
    assert cli.main(["server-generate", "--repo-dir", str(repo / "nope"), "--json"]) == 1


def test_every_new_message_in_two_languages():
    for code, (en, it) in MESSAGES.items():
        if code.startswith("index_"):
            assert en and it and en != it or code in ("index_entry_fields",), code
            assert set(re.findall(r"{(\w+)", en)) == set(re.findall(r"{(\w+)", it)), code
