"""MICRO-PL23 · updates (row X3 of the extensions plan).

Versions side by side (W-4): every data and code version on this machine,
going back to an older code without a download; «Update all» (an update that
would ask the trust again waits); the question «this file uses 1.0.0, 1.1.0
is here» (SPEC-pacchetto §11.3) and its answer; clean removal (one version,
the old code versions, what nothing owns, every source, the downloaded
archives, the plugin's own state only when asked); wheels per platform (only
this machine's are installed; ``build --split-platforms``; a repository with
one archive per platform, the client picking this machine's). The archives
are the SYNTHETIC ones of tests/data/profiles (D-5, marked ESEMPIO).
"""
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.extensions import remote as RM
from s3dgraphy.extensions import store as S
from s3dgraphy.profiles import store as P

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
ID = "esempio-statuaria"
IRI = "https://w3id.org/extendedmatrix/profile/esempio-statuaria"
WHEELS = {"macos-arm64": "numpy-2.1.0-cp311-cp311-macosx_11_0_arm64.whl",
          "windows-x64": "numpy-2.1.0-cp311-cp311-win_amd64.whl",
          "linux-x64": "numpy-2.1.0-cp311-cp311-manylinux_2_17_x86_64.whl"}
PURE = "tinylib-1.0.0-py3-none-any.whl"


@pytest.fixture(autouse=True)
def _own_state_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("S3DGRAPHY_PLUGINS_DATA_DIR", str(tmp_path / "plugins-data"))
    RM.set_fetcher(None)
    yield
    RM.set_fetcher(None)


def copy(src: Path, tmp_path: Path, name=None) -> Path:
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    return dst


def set_toml(folder: Path, pattern: str, repl: str):
    p = folder / "em-extension.toml"
    text, n = re.subn(pattern, repl, p.read_text(encoding="utf-8"), count=1, flags=re.M)
    assert n, pattern
    p.write_text(text, encoding="utf-8")


def bump_code(folder: Path, v: str, archive: str):
    set_toml(folder, r'^version = "[^"]+"', f'version = "{archive}"')
    set_toml(folder, r'(\[code\]\nversion = )"[^"]+"', rf'\1"{v}"')
    init = folder / "code" / "facemesh_fit" / "__init__.py"
    init.write_text(init.read_text(encoding="utf-8") + f"\n# {v}\n", encoding="utf-8")


def bump_mixed_data(folder: Path, v: str, archive: str):
    set_toml(folder, r'^version = "[^"]+"', f'version = "{archive}"')
    set_toml(folder, r'(\[data\]\nversion = )"[^"]+"', rf'\1"{v}"')
    for rel, key in (("data/profile.json", None), ("data/examples/testa-esempio.em.json", "ex")):
        f = folder / rel
        doc = json.loads(f.read_text(encoding="utf-8"))
        if key:
            doc["header"]["profiles"][0]["version"] = v
        else:
            doc["version"] = v
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def bump_separate(folder: Path, v: str, changelog: str = None):
    set_toml(folder, r'^version = "[^"]+"', f'version = "{v}"')
    for rel, ex in (("profile.json", False), ("examples/testa-esempio.em.json", True)):
        f = folder / rel
        doc = json.loads(f.read_text(encoding="utf-8"))
        if ex:
            doc["header"]["profiles"][0]["version"] = v
        else:
            doc["version"] = v
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if changelog is not None:
        (folder / "CHANGELOG.md").write_text(changelog, encoding="utf-8")


def with_wheels(folder: Path, plats=("macos-arm64", "windows-x64", "linux-x64"), pure=True):
    names = [WHEELS[p] for p in plats] + ([PURE] if pure else [])
    set_toml(folder, r'^platforms = .*$', "platforms = [" + ", ".join(f'"{p}"' for p in plats) + "]\n"
             "wheels = [" + ", ".join(f'"./wheels/{n}"' for n in names) + "]")
    w = folder / "code" / "wheels"
    w.mkdir(parents=True, exist_ok=True)
    for n in names:
        (w / n).write_bytes(b"PK\x05\x06" + b"\0" * 18)
    return folder


def row(eid=ID):
    return X.read_register()["extensions"].get(eid)


# ── versions side by side, and going back ───────────────────────────────────

def test_versions_side_by_side_and_going_back_without_a_download(tmp_path):
    X.install(MIXED, trust=True)
    v2 = copy(MIXED, tmp_path, "v2")
    bump_code(v2, "0.3.0", "0.1.1")
    out = X.update(v2)
    assert out["code"]["status"] == "installed" and out["code"]["version"] == "0.3.0"
    v3 = copy(MIXED, tmp_path, "v3")
    bump_mixed_data(v3, "0.2.0", "0.2.0")
    bump_code(v3, "0.3.0", "0.2.0")
    # the same code 0.3.0, so only the data move: 0.2.0 beside 0.1.0
    shutil.copy(v2 / "code" / "facemesh_fit" / "__init__.py", v3 / "code" / "facemesh_fit" / "__init__.py")
    X.update(v3)
    vs = X.versions(ID)
    assert [d["version"] for d in vs["data"]] == ["0.2.0", "0.1.0"] and vs["data"][0]["newest"]
    assert [(c["version"], c["source"], c["active"]) for c in vs["code"]] == [("0.3.0", "disk", True),
                                                                            ("0.1.0", "disk", False)]
    assert vs["code_version"] == "0.3.0" and vs["can_go_back"]
    back = X.use_code(ID, "0.1.0")
    assert back["active"] and back["previous"] == "0.3.0" and back["restart"]
    assert "prossimo avvio" in back["warnings"][0]["it"]
    assert row()["code"]["version"] == "0.1.0"
    assert [e["version"] for e in X.read_enabled()["plugins"].values()] == ["0.1.0"]
    assert X.versions(ID)["code"][1]["active"] and not X.versions(ID)["can_go_back"]
    X.use_code(ID, "0.3.0")
    assert row()["code"]["version"] == "0.3.0"
    with pytest.raises(X.ExtensionError) as e:
        X.use_code(ID, "9.9.9")
    assert e.value.report.codes() == ["code_version_absent"]


def test_going_back_to_a_version_trusted_with_other_permissions_asks_again(tmp_path):
    X.install(MIXED, trust=True)
    v2 = copy(MIXED, tmp_path, "v2")
    bump_code(v2, "0.3.0", "0.1.1")
    set_toml(v2, r'^(  files = .*)$', r'\1\n  network = "Scarica il modello di riferimento dal suo archivio"')
    assert X.preview(v2)["code"]["trust_changes"] == ["permissions"]
    X.update(v2, trust=True)
    with pytest.raises(X.ExtensionError) as e:
        X.use_code(ID, "0.1.0")
    assert e.value.report.codes() == ["code_trust_required_for"]
    assert X.use_code(ID, "0.1.0", trust=True)["version"] == "0.1.0"


# ── clean removal ───────────────────────────────────────────────────────────

def test_one_version_the_old_ones_and_never_the_one_in_use(tmp_path):
    X.install(MIXED, trust=True)
    for i, v in enumerate(("0.3.0", "0.4.0"), 1):
        d = copy(MIXED, tmp_path, f"v{i}")
        bump_code(d, v, f"0.1.{i}")
        X.update(d)
    assert [c["version"] for c in X.versions(ID)["code"]] == ["0.4.0", "0.3.0", "0.1.0"]
    with pytest.raises(X.ExtensionError) as e:
        X.remove_version(ID, "code", "0.4.0")
    assert e.value.report.codes() == ["code_version_active"]
    assert "usa prima un'altra versione" in str(e.value.report.problems[0].text("it"))
    out = X.remove_version(ID, "code", "0.1.0")
    assert out["code_removed"] == ["disk/0.1.0"] and out["code_versions"] == ["0.3.0", "0.4.0"]
    assert not (X.plugins_dir() / "disk" / ID / "0.1.0").exists()
    assert X.prune_code(ID)["code_removed"] == ["disk/0.3.0"]
    assert [c["version"] for c in X.versions(ID)["code"]] == ["0.4.0"]
    assert row()["code"]["versions"] == ["0.4.0"]
    # a data version, one at a time (documents are bound to them)
    d = copy(MIXED, tmp_path, "data2")
    bump_mixed_data(d, "0.2.0", "0.2.0")
    bump_code(d, "0.4.0", "0.2.0")
    shutil.copy(tmp_path / "v2" / "code" / "facemesh_fit" / "__init__.py", d / "code" / "facemesh_fit" / "__init__.py")
    X.update(d)
    assert X.remove_version(ID, "data", "0.1.0")["data_removed"] == ["0.1.0"]
    assert row()["data"]["versions"] == ["0.2.0"]


def test_removing_a_package_leaves_nothing_but_what_the_person_keeps(tmp_path):
    X.install(MIXED, trust=True)
    # the same package later from a repository: its code under a second source
    S.install(MIXED, trust=True, source_name="lab")
    assert {f.parent.parent.name for f in X.code_folders(ID)} == {"disk", "lab"}
    arch = X.extensions_dir() / "archives" / "lab"
    arch.mkdir(parents=True)
    (arch / f"{ID}-0.1.0.zip").write_bytes(b"x")
    (arch / "other-thing-1.0.0.zip").write_bytes(b"x")
    state = tmp_path / "plugins-data" / ID
    state.mkdir(parents=True)
    (state / "settings.json").write_text("{}")
    out = X.remove(ID)
    assert out["archives_removed"] == [f"lab/{ID}-0.1.0.zip"]
    assert out["user_data"] == {"path": str(state), "removed": False} and state.is_dir()
    assert X.code_folders(ID) == [] and not any((X.plugins_dir() / s / ID).exists() for s in ("disk", "lab"))
    assert (arch / "other-thing-1.0.0.zip").is_file() and row() is None and P.installed() == []
    assert X.read_enabled()["plugins"] == {}
    # the box ticked: the plugin's own state goes too
    X.install(PLUGIN, trust=True)
    st = tmp_path / "plugins-data" / "facemesh_fit"
    st.mkdir(parents=True)
    out = X.remove("facemesh_fit", purge_user_data=True)
    assert out["user_data"]["removed"] and not st.exists() and row("facemesh_fit") is None


def test_leftovers_are_found_and_cleaned_and_the_installed_untouched(tmp_path):
    X.install(MIXED, trust=True)
    base = X.plugins_dir()
    ghost = base / "disk" / "ghost" / "1.0.0"
    ghost.mkdir(parents=True)
    (ghost / ".install.json").write_text("{}")
    (base / "disk" / ID / ".0.9.0-abc123").mkdir()
    arch = X.extensions_dir() / "archives" / "nas"
    arch.mkdir(parents=True)
    (arch / "ghost-1.0.0.zip").write_bytes(b"x")
    (arch / f"{ID}-0.1.0.zip").write_bytes(b"x")
    found = X.leftovers()
    assert [x["path"] for x in found["code"]] == ["disk/ghost/1.0.0"]
    assert [x["path"] for x in found["partial"]] == [f"disk/{ID}/.0.9.0-abc123"]
    assert [x["path"] for x in found["archives"]] == ["nas/ghost-1.0.0.zip"] and found["count"] == 3
    assert X.clean(dry_run=True)["removed"] is False and ghost.exists()
    assert X.clean()["removed"] and X.leftovers()["count"] == 0
    assert not (base / "disk" / "ghost").exists() and (arch / f"{ID}-0.1.0.zip").is_file()
    assert [c["version"] for c in X.versions(ID)["code"]] == ["0.1.0"]


# ── wheels per platform ─────────────────────────────────────────────────────

def test_only_the_wheels_of_this_machine_are_installed(tmp_path):
    pkg = with_wheels(copy(MIXED, tmp_path))
    out = X.install(pkg, trust=True, platform_name="linux-x64")
    assert out["code"]["status"] == "installed"
    folder = X.plugins_dir() / "disk" / ID / "0.1.0"
    assert sorted(p.name for p in (folder / "wheels").iterdir()) == sorted([WHEELS["linux-x64"], PURE])
    meta = json.loads((folder / ".install.json").read_text())
    assert meta["platform"] == "linux-x64"
    assert meta["wheels_skipped"] == sorted([WHEELS["macos-arm64"], WHEELS["windows-x64"]])
    assert X.versions(ID)["code"][0]["wheels_skipped"] == meta["wheels_skipped"]


def test_build_split_platforms_one_archive_per_platform_with_its_wheels(tmp_path):
    pkg = with_wheels(copy(MIXED, tmp_path))
    out_dir = tmp_path / "dist"
    res = X.build(pkg, output_dir=out_dir, split_platforms=True)
    assert res["ok"] and res["written"], res
    assert [x["platform"] for x in res["split"]] == ["macos-arm64", "windows-x64", "linux-x64"]
    assert sorted(p.name for p in out_dir.iterdir()) == sorted(f"{ID}-0.1.0-{p}.zip" for p in WHEELS)
    for x in res["split"]:
        with zipfile.ZipFile(x["path"]) as z:
            whl = sorted(Path(n).name for n in z.namelist() if n.endswith(".whl"))
            env = z.read("em-extension.toml").decode()
        assert whl == sorted([WHEELS[x["platform"]], PURE])
        assert f'platforms = ["{x["platform"]}"]' in env
        assert X.validate_archive(x["path"]).ok
    # one platform only: said, one archive for all
    one = with_wheels(copy(MIXED, tmp_path, "one"), plats=("linux-x64",))
    r1 = X.build(one, output_dir=tmp_path / "d1", split_platforms=True)
    assert r1["ok"] and "split" not in r1 and [c["code"] for c in r1["changes"]][-1] == "build_split_none"
    # the command line
    assert cli.main(["build", str(pkg), "--output-dir", str(tmp_path / "d2"), "--split-platforms"]) == 0
    assert len(list((tmp_path / "d2").glob("*.zip"))) == 3


def test_a_repository_with_one_archive_per_platform_and_the_client_picks_this_machine(tmp_path, monkeypatch):
    pkg = with_wheels(copy(MIXED, tmp_path))
    repo = tmp_path / "repo"
    assert X.build(pkg, output_dir=repo, split_platforms=True)["ok"]
    gen = X.server_generate(repo)
    assert gen["ok"], gen["problems"]
    data = gen["index"]["data"]
    assert [(e["id"], e["version"], e["platforms"]) for e in data] == \
        [(ID, "0.1.0", [p]) for p in sorted(WHEELS)]
    assert not [w for x in gen["listed"] for w in x["warnings"] if w["code"] == "index_file_name"]
    # an archive for every platform beside them is a twin
    assert X.build(pkg, output_dir=repo)["ok"]
    bad = X.server_generate(repo, dry_run=True)
    assert not bad["ok"] and [p["code"] for x in bad["refused"] for p in x["errors"]] == ["index_duplicate"]
    (repo / f"{ID}-0.1.0.zip").unlink()
    X.server_generate(repo)
    X.add_repository(str(repo), name="lab")
    X.sync()
    monkeypatch.setattr(RM, "this_platform", lambda: "windows-x64")
    av = X.available()
    assert [(a["id"], a["version"]) for a in av["available"]] == [(ID, "0.1.0")] and av["other_platforms"] == []
    got = X.download("lab", ID)
    assert got["entry"]["platforms"] == ["windows-x64"] and got["path"].endswith(f"{ID}-0.1.0-windows-x64.zip")
    out = X.install_from("lab", ID, trust=True, platform_name="windows-x64")
    assert out["installed"]["code"]["status"] == "installed"
    folder = X.plugins_dir() / "lab" / ID / "0.1.0" / "wheels"
    assert sorted(p.name for p in folder.iterdir()) == sorted([WHEELS["windows-x64"], PURE])
    # a machine no archive is for: said, never offered, never installed
    monkeypatch.setattr(RM, "this_platform", lambda: "linux-arm64")
    av = X.available()
    assert av["available"] == [] and av["other_platforms"][0]["id"] == ID
    assert "non per questa macchina (linux-arm64)" in av["other_platforms"][0]["problem"]["it"]
    with pytest.raises(X.RepoError) as e:
        X.install_from("lab", ID)
    assert e.value.report.codes() == ["repo_other_platforms"]


# ── «Update all» ────────────────────────────────────────────────────────────

def test_update_all_updates_and_an_update_that_asks_the_trust_again_waits(tmp_path):
    repo = tmp_path / "nas"
    repo.mkdir()
    for src in (SEPARATE, PLUGIN):
        assert X.build(src, output_dir=repo)["ok"]
    X.server_generate(repo)
    X.add_repository(str(repo), name="nas")
    X.sync()
    X.install_from("nas", "facemesh_fit", trust=True, trust_requires=True)
    assert X.update_all()["up_to_date"]
    sep = copy(SEPARATE, tmp_path, "sep")
    bump_separate(sep, "0.1.1")
    fm = copy(PLUGIN, tmp_path, "fm")
    set_toml(fm, r'^version = "0.2.0"$', 'version = "0.2.1"')
    set_toml(fm, r'^(  files = .*)$', r'\1\n  network = "Scarica il modello di riferimento dal suo archivio"')
    for src in (sep, fm):
        assert X.build(src, output_dir=repo)["ok"]
    X.server_generate(repo)
    chk = X.check_updates()
    assert chk["repositories"][0]["ok"]
    by = {u["id"]: u for u in chk["updates"]}
    assert by[ID]["trust_needed"] is False and by[ID]["code"] is False
    assert by["facemesh_fit"]["trust_needed"] and by["facemesh_fit"]["trust_changes"] == ["permissions"]
    res = X.update_all()
    assert [(u["id"], u["from"], u["to"]) for u in res["updated"]] == [(ID, "0.1.0", "0.1.1")]
    assert [n["id"] for n in res["needs_trust"]] == ["facemesh_fit"] and res["failed"] == []
    assert "chiede di nuovo la fiducia" in res["needs_trust"][0]["problem"]["it"]
    assert row("facemesh_fit")["code"]["version"] == "0.2.0"          # nothing of it written
    assert sorted(row()["data"]["versions"]) == ["0.1.0", "0.1.1"]   # beside, W-4
    res = X.update_all(trust=["facemesh_fit"])
    assert [u["id"] for u in res["updated"]] == ["facemesh_fit"] and res["needs_trust"] == []
    assert row("facemesh_fit")["code"]["version"] == "0.2.1"
    assert X.update_all()["up_to_date"]
    # the command line
    assert cli.main(["update-all"]) == 0 and cli.main(["updates"]) == 0


def test_a_code_left_out_stays_out_and_the_data_update(tmp_path):
    repo = tmp_path / "nas"
    repo.mkdir()
    assert X.build(MIXED, output_dir=repo)["ok"]
    X.server_generate(repo)
    X.add_repository(str(repo), name="nas")
    X.sync()
    X.install_from("nas", ID, parts="data")
    assert row()["code"]["status"] == "not_installed"
    v2 = copy(MIXED, tmp_path, "v2")
    bump_mixed_data(v2, "0.2.0", "0.2.0")
    assert X.build(v2, output_dir=repo)["ok"]
    X.server_generate(repo)
    up, = X.check_updates()["updates"]
    assert up["code_left_out"] and not up["trust_needed"]
    res = X.update_all()
    assert res["updated"][0]["data"] == "installed" and row()["code"]["status"] == "not_installed"


# ── a document's question ───────────────────────────────────────────────────

def test_this_file_uses_one_version_and_a_newer_is_here(tmp_path):
    X.install(SEPARATE)
    declared = [{"iri": IRI, "version": "0.1.0"}]
    assert X.document_updates(declared) == []
    p1 = copy(SEPARATE, tmp_path, "p1")
    bump_separate(p1, "0.1.1")
    X.install(p1)
    u, = X.document_updates(declared)
    assert (u["name"], u["declared"], u["newest"], u["change"], u["ask_content"]) == (ID, "0.1.0", "0.1.1", "patch", False)
    assert u["problem"]["it"] == f"questo file usa {ID} 0.1.0, c'è la 0.1.1: aggiornare la dichiarazione?"
    assert u["changelog"] is None and u["declared_installed"]
    # 0.x: a new minor changes the content — the CHANGELOG is shown, only what is new
    p2 = copy(SEPARATE, tmp_path, "p2")
    bump_separate(p2, "0.2.0", changelog="# Changelog\n\n## 0.2.0\n\n- nuovi punti del volto\n\n"
                                         "## 0.1.1\n\n- correzioni\n\n## 0.1.0\n\n- prima versione\n")
    X.install(p2)
    u, = X.document_updates(declared)
    assert (u["newest"], u["change"], u["ask_content"]) == ("0.2.0", "major", True)
    assert u["changelog"]["sections"] == ["0.2.0", "0.1.1"] and "prima versione" not in u["changelog"]["text"]
    assert "cambia il contenuto" in u["problem"]["it"]
    assert X.document_updates([{"iri": IRI, "version": "0.2.0"}]) == []
    # the answer: the declaration rewritten, the rest kept in its order
    other = {"iri": "https://example.org/profile/altro", "version": "1.0.0"}
    new = X.redeclare([other, declared[0]], ID, "0.2.0")
    assert new == [other, {"iri": IRI, "version": "0.2.0"}]
    with pytest.raises(X.ExtensionError):
        X.redeclare(declared, ID, "9.0.0")


def test_a_mixed_package_keeps_its_changelog_beside_the_data(tmp_path):
    pkg = copy(MIXED, tmp_path)
    (pkg / "CHANGELOG.md").write_text("## 0.1.0\n\n- prima versione (ESEMPIO)\n", encoding="utf-8")
    X.install(pkg, trust=True)
    log = X.changelog(ID, "0.1.0")
    assert log["file"] == "CHANGELOG.md" and log["sections"] == ["0.1.0"]


def test_the_document_question_from_the_command_line_and_em(tmp_path, capsys):
    X.install(SEPARATE)
    p1 = copy(SEPARATE, tmp_path, "p1")
    bump_separate(p1, "0.1.1")
    X.install(p1)
    doc = SEPARATE / "examples" / "testa-esempio.em.json"
    assert cli.main(["document", str(doc)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [(u["declared"], u["newest"]) for u in out["updates"]] == [("0.1.0", "0.1.1")]
    from s3dgraphy import em
    from s3dgraphy.em.host import ScriptHost
    em.host.install(ScriptHost())
    try:
        em.open(str(doc))
        assert [u["newest"] for u in em.extensions.document_updates()] == ["0.1.1"]
        assert em.extensions.redeclare(ID, "0.1.1") == [{"iri": IRI, "version": "0.1.1"}]
        assert em.extensions.document_updates() == []
        # the save writes the new declaration
        out = tmp_path / "saved.em.json"
        em.save(str(out))
        assert json.loads(out.read_text())["header"]["profiles"] == [{"iri": IRI, "version": "0.1.1"}]
    finally:
        em.host.uninstall()


def test_every_x3_message_is_in_english_and_italian():
    from s3dgraphy.profiles.problems import MESSAGES
    for code in ("repo_other_platforms", "update_needs_trust", "build_split_none", "code_version_absent",
                 "code_version_active", "code_trust_required_for", "code_switched", "document_newer_minor",
                 "document_newer_major"):
        en, it = MESSAGES[code]
        assert set(re.findall(r"{(\w+)", en)) == set(re.findall(r"{(\w+)", it)), code
