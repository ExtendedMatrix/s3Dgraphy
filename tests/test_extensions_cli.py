"""MICRO-PL05 · ``python -m s3dgraphy.extensions validate|build`` (row W19).

The curator checks and packs without opening EMStudio, with the validator the
Extensions window uses. The archives are the SYNTHETIC ones of
tests/data/profiles (D-5, marked ESEMPIO); a bare 0.1 profile is the real
``example-toolmarks`` of the vocabularies repository when it is beside this
one, and a bare copy of the synthetic package always.
"""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy import profiles as P
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.profiles.package import _toml
from s3dgraphy.profiles.problems import MESSAGES

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
TOOLMARKS = Path(__file__).resolve().parents[2] / "vocabularies" / "profiles" / "example-toolmarks"
STAT_IRI = "https://w3id.org/extendedmatrix/profile/esempio-statuaria"


def copy(src: Path, tmp_path: Path, name=None) -> Path:
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    return dst


def set_toml(folder: Path, pattern: str, repl: str, count=1):
    p = folder / "em-extension.toml"
    text, n = re.subn(pattern, repl, p.read_text(encoding="utf-8"), count=count, flags=re.M)
    assert n, pattern
    p.write_text(text, encoding="utf-8")


def codes(target, level=None):
    return X.validate_archive(target).codes(level)


def tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(folder)).encode() + p.read_bytes())
    return h.hexdigest()


def bare(tmp_path: Path) -> Path:
    """The synthetic data package as a bare profile: no envelope, the
    vocabulary files named in qualia_vocabularies[].path (0.1 style)."""
    pkg = copy(SEPARATE, tmp_path)
    (pkg / "em-extension.toml").unlink()
    prof = json.loads((pkg / "profile.json").read_text(encoding="utf-8"))
    files = {"lavorazione": "vocab/lavorazione.ttl", "fase-superficie": "vocab/fase-superficie.ttl"}
    for q in prof["qualia_vocabularies"]:
        q["path"] = files[q["scheme"].rstrip("/").rsplit("/", 1)[-1]]
    (pkg / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    (pkg / "vocab" / "punti-volto.ttl").unlink()  # not named by qualia_vocabularies: the landmark set's own
    return pkg


# ── validate: the same validator as the window ─────────────────────────────

def test_the_synthetic_archives_validate():
    for src in (SEPARATE, PLUGIN, MIXED):
        assert X.validate_archive(src).ok, src
    assert "type_missing" in codes(SEPARATE, "warning")
    assert "type_missing" in codes(PLUGIN, "warning")
    assert "type_missing" not in codes(MIXED)


def test_the_window_preview_says_the_same_warnings():
    pv = X.preview(SEPARATE)
    assert "type_missing" in [w["code"] for w in pv["warnings"]]


def test_a_folder_and_its_zip_say_the_same(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    set_toml(pkg, r'fascia = "A"', 'fascia = "Z"')
    z = tmp_path / "s.zip"
    with zipfile.ZipFile(z, "w") as out:
        for f in sorted(pkg.rglob("*")):
            if f.is_file():
                out.write(f, f.relative_to(pkg).as_posix())
    assert codes(pkg) == codes(z) and "vocab_tier_bad" in codes(z, "error")


@pytest.mark.parametrize("license,tier,code", [
    ("SPDX:CC-BY-SA-4.0", "A", "vocab_tier_less_prudent"),
    ("SPDX:LicenseRef-IAA", "B", "vocab_tier_less_prudent"),
    ("SPDX:CC-BY-4.0", "Z", "vocab_tier_bad"),
    ("SPDX:CC-BY-4.0", "C", "vocab_tier_c_file"),
    ("SPDX:CC-BY-4.0", "B", None),            # more prudent than the licence: allowed
    ("SPDX:CC-BY-SA-4.0", "B", None),
])
def test_the_tier_is_checked_against_the_licence(tmp_path, license, tier, code):
    pkg = copy(SEPARATE, tmp_path)
    set_toml(pkg, r'license = "SPDX:CC-BY-4.0"\n  fascia = "A"', f'license = "{license}"\n  fascia = "{tier}"')
    r = X.validate_archive(pkg)
    if code is None:
        assert r.ok, r.codes()
    else:
        assert code in r.codes("error")
        assert "data_vocabulary" not in r.codes()  # said once, with its code, not again by the planner
        p = next(x for x in r.problems if x.code == code)
        assert p.text("it") != p.text("en") and "#1" in p.where


def test_a_carried_vocabulary_without_licence_digest_or_pointer(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    set_toml(pkg, r'  license = "SPDX:CC-BY-4.0"\n', "")
    assert "vocab_license_missing" in codes(pkg, "error")
    pkg = copy(SEPARATE, tmp_path, "b")
    set_toml(pkg, r'  digest = "sha256:[0-9a-f]+"\n', "")
    assert "vocab_digest_missing" in codes(pkg, "error")
    pkg = copy(SEPARATE, tmp_path, "c")
    set_toml(pkg, r'  path = "vocab/punti-volto.ttl"\n', "")
    assert "vocab_path_missing" in codes(pkg, "error")
    pkg = copy(SEPARATE, tmp_path, "d")
    set_toml(pkg, r'  path = "vocab/punti-volto.ttl"\n(.*\n.*\n)  license = "SPDX:CC-BY-4.0"\n  fascia = "A"',
             r'\1  license = "SPDX:LicenseRef-x"\n  fascia = "C"')
    assert "vocab_tier_c_fetch" in codes(pkg, "error")


def test_a_bare_profile_is_read_and_said(tmp_path):
    pkg = bare(tmp_path)
    r = X.validate_archive(pkg)
    assert r.ok, [str(p) for p in r.errors]
    assert "bare_profile" in r.codes("warning")


def test_the_code_section_as_an_archive(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    set_toml(pkg, r'^(platforms = .*)$', r'\1\nwheels = ["./wheels/numpy.whl", "./wheels/attrs-24.2.0-py3-none-any.whl"]')
    (pkg / "wheels").mkdir()
    (pkg / "wheels" / "numpy.whl").write_bytes(b"PK")
    c = codes(pkg, "error")
    assert "code_wheel_name" in c and "code_wheel_missing" in c
    (pkg / "wheels" / "attrs-24.2.0-py3-none-any.whl").write_bytes(b"PK")
    (pkg / "wheels" / "numpy.whl").unlink()
    set_toml(pkg, r'"\./wheels/numpy\.whl", ', "")
    assert X.validate_archive(pkg).ok  # a pure wheel runs on every platform
    set_toml(pkg, r'^platforms = .*$', 'platforms = ["macos-arm64", "amiga-68k"]')
    assert "code_platform_unknown" in codes(pkg, "error")
    set_toml(pkg, r'^platforms = .*\n', "")
    set_toml(pkg, r'"\./wheels/attrs', '"./wheels/numpy-2.1.0-cp311-cp311-win_amd64.whl", "./wheels/attrs')
    (pkg / "wheels" / "numpy-2.1.0-cp311-cp311-win_amd64.whl").write_bytes(b"PK")
    r = X.validate_archive(pkg)
    assert r.ok and "code_platforms_undeclared" in r.codes("warning")


def test_the_code_root_must_exist(tmp_path):
    pkg = copy(MIXED, tmp_path)
    set_toml(pkg, r'root = "code/"', 'root = "codice/"')
    assert "code_outside_root" in codes(pkg, "error")


def test_every_message_of_w19_speaks_both_languages():
    w19 = [k for k in MESSAGES if k.startswith(("vocab_tier", "vocab_digest", "build_", "code_platform", "code_wheel_name",
                                                 "code_outside", "type_missing", "bare_profile", "vocab_path"))]
    assert len(w19) >= 25
    for k in w19:
        en, it = MESSAGES[k]
        assert en and it, k


# ── build ───────────────────────────────────────────────────────────────────

def test_build_writes_type_and_leaves_the_folder_alone(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    before = tree_hash(pkg)
    out = X.build(pkg, output_dir=tmp_path / "out")
    assert out["ok"] and out["written"] and out["file"] == "esempio-statuaria-0.1.0.zip"
    assert tree_hash(pkg) == before
    assert {c["code"] for c in out["changes"]} >= {"build_written", "build_requires_profile", "build_requires_core"}
    z = Path(out["path"])
    env = _toml(zipfile.ZipFile(z).read("em-extension.toml").decode())
    assert env["type"] == "community-package" and env["requires"]["core"] == {"em": ">=1.6,<1.7"}
    prof = json.loads(zipfile.ZipFile(z).read("profile.json"))
    assert prof["requires"]["plugins"] == [{"id": "facemesh_fit", "version": "^0.2", "optional": True}]
    r = X.validate_archive(z)
    assert r.ok and "type_missing" not in r.codes()
    assert out["archive_hash"] == X.archive_hash(P.open_package(z))
    assert set(out["digests"]) == {"data"}


def test_build_is_deterministic(tmp_path):
    a = X.build(MIXED, output_dir=tmp_path / "a")
    b = X.build(MIXED, output_dir=tmp_path / "b")
    assert Path(a["path"]).read_bytes() == Path(b["path"]).read_bytes()
    assert a["changes"] == []  # the mixed example is complete: its envelope is taken byte for byte
    assert zipfile.ZipFile(a["path"]).read("em-extension.toml") == (MIXED / "em-extension.toml").read_bytes()
    assert set(a["digests"]) == {"data", "code"}


def test_build_defaults_to_the_folder_and_does_not_take_its_own_archives(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    (pkg / "facemesh_fit" / "__pycache__").mkdir()
    (pkg / "facemesh_fit" / "__pycache__" / "x.cpython-39.pyc").write_bytes(b"\0")
    (pkg / ".DS_Store").write_bytes(b"\0")
    first = X.build(pkg)
    assert Path(first["path"]).parent == pkg
    second = X.build(pkg)
    names = zipfile.ZipFile(second["path"]).namelist()
    assert names == sorted(["LICENSE", "em-extension.toml", "facemesh_fit/__init__.py"])
    assert first["archive_hash"] == second["archive_hash"]


def test_build_paths_and_excludes(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    (pkg / "notes").mkdir()
    (pkg / "notes" / "draft.md").write_text("x")
    set_toml(pkg, r'^(\[code\])', '[build]\npaths = ["facemesh_fit", "LICENSE"]\n\n\\1')
    names = zipfile.ZipFile(X.build(pkg, output_dir=tmp_path / "o")["path"]).namelist()
    assert "notes/draft.md" not in names and "facemesh_fit/__init__.py" in names and "em-extension.toml" in names
    assert X.select_files(P.package.Source(pkg), {"build": {"paths_exclude_pattern": ["/notes/", "LICENSE"]}}) == \
        ["em-extension.toml", "facemesh_fit/__init__.py"]


def test_build_computes_the_digests(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    ttl = pkg / "vocab" / "lavorazione.ttl"
    ttl.write_text(ttl.read_text() + "\n# a curator's note\n")
    form = pkg / "forms" / "stat-scheda-superficie" / "0.1.0.json"
    form.write_text(form.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert {"vocab_digest_mismatch", "form_digest"} <= set(codes(pkg, "error"))
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert out["ok"], out["errors"]
    said = " | ".join(c["en"] for c in out["changes"] if c["code"] == "build_digest")
    assert "vocab/lavorazione.ttl: digest" in said and "forms/stat-scheda-superficie/0.1.0.json: digest" in said
    assert X.validate_archive(out["path"]).ok


def test_build_moves_the_vocabulary_paths_of_a_bare_profile(tmp_path):
    pkg = bare(tmp_path)
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert out["ok"], out["errors"]
    cs = [c["code"] for c in out["changes"]]
    assert cs.count("build_moved") == 2 and "build_envelope_made" in cs and cs.count("build_digest") == 2
    z = zipfile.ZipFile(out["path"])
    env = _toml(z.read("em-extension.toml").decode())
    assert env["id"] == "esempio-statuaria" and env["type"] == "community-package"
    assert env["license"] == ["SPDX:CC-BY-4.0"] and env["maintainer"] == "@zalmoxes-laran"
    assert {v["fascia"] for v in env["data"]["vocabularies"]} == {"A"}
    assert all(v["digest"].startswith("sha256:") for v in env["data"]["vocabularies"])
    prof = json.loads(z.read("profile.json"))
    assert not any("path" in q for q in prof["qualia_vocabularies"])
    assert env["requires"]["core"] == {"em": ">=1.6,<1.7"}
    # and the archive installs (W21): the vocabularies go to the manager
    res = X.install(out["path"])
    assert res["data"]["status"] == "installed"
    assert len(res["data"]["vocabularies"]["installed"]) == 2


@pytest.mark.skipif(not TOOLMARKS.exists(), reason="the vocabularies repository is not beside this one")
def test_build_the_real_bare_profile_example_toolmarks(tmp_path):
    before = tree_hash(TOOLMARKS)
    out = X.build(TOOLMARKS, output_dir=tmp_path)
    assert out["ok"] and out["file"] == "example-toolmarks-0.1.0.zip", out["errors"]
    assert tree_hash(TOOLMARKS) == before
    assert X.install(out["path"])["data"]["status"] == "installed"


def test_build_refuses_and_writes_nothing(tmp_path):
    pkg = copy(SEPARATE, tmp_path)
    set_toml(pkg, r'license = "SPDX:CC-BY-4.0"\n  fascia = "A"', 'license = "SPDX:CC-BY-SA-4.0"\n  fascia = "A"')
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert not out["ok"] and not out["written"] and out["path"] is None
    assert not (tmp_path / "o").exists()
    assert out["errors"][-1]["code"] == "build_refused"
    assert "vocab_tier_less_prudent" in [e["code"] for e in out["errors"]]


def test_build_a_bare_profile_without_licence_for_its_vocabulary(tmp_path):
    pkg = bare(tmp_path)
    prof = json.loads((pkg / "profile.json").read_text(encoding="utf-8"))
    prof["license"] = ["CC-BY-4.0", "CC0-1.0"]
    (pkg / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert not out["ok"] and "build_vocab_license" in [e["code"] for e in out["errors"]]


def test_build_translates_requires_profiles_by_iri(tmp_path):
    P.install(SEPARATE)  # the machine knows esempio-statuaria by its IRI
    pkg = copy(PLUGIN, tmp_path)
    set_toml(pkg, r'^extensions = .*$', f'profiles = [{{ iri = "{STAT_IRI}", version = "^0.1" }}]')
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert out["ok"], out["errors"]
    assert "build_requires_translated" in [c["code"] for c in out["changes"]]
    env = _toml(zipfile.ZipFile(out["path"]).read("em-extension.toml").decode())
    assert env["requires"] == {"extensions": [{"id": "esempio-statuaria", "version": "^0.1", "part": "data"}]}


def test_build_a_bare_profile_with_a_mandatory_plugin(tmp_path):
    pkg = bare(tmp_path)
    prof = json.loads((pkg / "profile.json").read_text(encoding="utf-8"))
    prof["requires"]["plugins"] = [{"id": "facemesh_fit", "version": "^0.2"}]
    (pkg / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    out = X.build(pkg, output_dir=tmp_path / "o")
    assert out["ok"], out["errors"]
    assert "build_code_optional" in [c["code"] for c in out["changes"]]
    env = _toml(zipfile.ZipFile(out["path"]).read("em-extension.toml").decode())
    assert env["requires"]["extensions"] == [{"id": "facemesh_fit", "version": "^0.2", "part": "code", "optional": True}]


def test_build_needs_a_folder(tmp_path):
    z = X.build(MIXED, output_dir=tmp_path)["path"]
    with pytest.raises(X.ExtensionError) as e:
        X.build(z)
    assert e.value.report.codes() == ["build_folder"]


def test_toml_written_reads_back():
    for src in (SEPARATE, PLUGIN, MIXED):
        env = _toml((src / "em-extension.toml").read_text(encoding="utf-8"))
        assert _toml(X.dump_toml(env)) == env
    tricky = {"id": "x", "name": 'Quote " and \\ and è', "data": {"vocabularies": [
        {"scheme": "s", "fetch": {"url": "https://x/y", "digest": "sha256:0"}}]}, "requires": {"core": {"em": ">=1.6"}}}
    assert _toml(X.dump_toml(tricky)) == tricky


# ── the command line ────────────────────────────────────────────────────────

def test_cli_validate(tmp_path, capsys):
    assert cli.main(["validate", str(SEPARATE), str(MIXED)]) == 0
    assert "build writes 'community-package'" in capsys.readouterr().out
    broken = copy(SEPARATE, tmp_path)
    set_toml(broken, r'fascia = "A"', 'fascia = "Z"')
    assert cli.main(["validate", str(broken), "--lang", "it"]) == 1
    assert "fascia 'Z' — A, B o C" in capsys.readouterr().out
    assert cli.main(["validate", "--json", str(broken)]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc[str(broken)]["ok"] is False


def test_cli_build(tmp_path, capsys):
    pkg = copy(SEPARATE, tmp_path)
    assert cli.main(["build", str(pkg), "--output-dir", str(tmp_path / "o"), "--dry-run"]) == 0
    assert "dry run" in capsys.readouterr().out and not (tmp_path / "o").exists()
    assert cli.main(["--lang", "it", "build", str(pkg), "--output-dir", str(tmp_path / "o")]) == 0
    out = capsys.readouterr().out
    assert "scritto type = 'community-package'" in out and (tmp_path / "o" / "esempio-statuaria-0.1.0.zip").is_file()
    assert cli.main(["build", str(tmp_path / "o" / "esempio-statuaria-0.1.0.zip")]) == 1
    assert "build reads a folder" in capsys.readouterr().err
    assert cli.main(["build", "--json", str(pkg), "--output-dir", str(tmp_path / "j")]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
