"""MICRO-PL04 · s3dgraphy.extensions — installing by parts (row W21).

The archives are the SYNTHETIC ones of tests/data/profiles (D-5, marked
ESEMPIO): «esempio-statuaria» separate (data; the plugin facemesh_fit) and
mixed (one archive, data/ + code/). Every test has its own vocabulary,
profile, plugin and register folders (conftest.py).
"""
import json
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy import profiles as P
from s3dgraphy import vocabularies as V
from s3dgraphy.extensions import __main__ as cli

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
ID = "esempio-statuaria"


def copy(src: Path, tmp_path: Path, name=None) -> Path:
    dst = tmp_path / (name or src.name)
    shutil.copytree(src, dst)
    return dst


def set_toml(folder: Path, pattern: str, repl: str, count=1):
    p = folder / "em-extension.toml"
    text, n = re.subn(pattern, repl, p.read_text(encoding="utf-8"), count=count, flags=re.M)
    assert n, pattern
    p.write_text(text, encoding="utf-8")


def bump(folder: Path, archive=None, data=None, code=None):
    """New versions for the archive and its sections (the profile follows [data])."""
    if archive:
        set_toml(folder, r'^version = "[^"]+"', f'version = "{archive}"')
    if data:
        set_toml(folder, r'(\[data\]\nversion = )"[^"]+"', rf'\1"{data}"')
        prof = folder / "data" / "profile.json"
        doc = json.loads(prof.read_text(encoding="utf-8"))
        doc["version"] = data
        prof.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        ex = folder / "data" / "examples" / "testa-esempio.em.json"
        doc = json.loads(ex.read_text(encoding="utf-8"))
        doc["header"]["profiles"][0]["version"] = data
        ex.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if code:
        set_toml(folder, r'(\[code\]\nversion = )"[^"]+"', rf'\1"{code}"')
        init = folder / "code" / "facemesh_fit" / "__init__.py"
        init.write_text(init.read_text(encoding="utf-8") + f"\n# {code}\n", encoding="utf-8")


def zip_of(folder: Path, tmp_path: Path) -> Path:
    out = tmp_path / (folder.name + ".zip")
    with zipfile.ZipFile(out, "w") as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return out


def plugin_folder(eid=ID, version="0.1.0") -> Path:
    return X.plugins_dir() / "disk" / eid / version


def row(eid=ID):
    return X.read_register()["extensions"].get(eid)


def nothing_written():
    return not (X.extensions_dir() / "installed.json").exists() and not P.installed() and not V.vocab_installed() \
        and not (X.plugins_dir() / "disk").exists()


# ── the preview: two panels, nothing written ────────────────────────────────

def test_preview_shows_both_panels_and_writes_nothing():
    pv = X.preview(MIXED)
    assert pv["ok"] and pv["kind"] == "mixed" and pv["errors"] == []
    d, c = pv["data"], pv["code"]
    assert d["installable"] and d["update"] == "new" and d["version"] == "0.1.0"
    s = d["summary"]
    assert [v["fascia"] for v in s["vocabularies"]] == ["A", "A", "A"]
    assert all(v["license"] == "SPDX:CC-BY-4.0" for v in s["vocabularies"])
    assert (s["qualia"], s["extractors"], s["landmark_sets"], s["combiners"], s["forms"], s["color_schemes"]) == \
        (4, 3, 1, 3, 1, 1)
    assert s["primitives"] == ["point", "polyline", "surface"]
    assert c["installable"] and c["verified"] is False and c["source"] == "disk"
    assert c["permissions"] == {"files": "Legge le texture del modello per riconoscere il volto"}
    assert c["capabilities"] == ["read-graph", "ingest-batch"]
    assert c["commands"][0]["in"] == ["context.node@1", "menu.tools@1"]
    assert c["trust_needed"] is True and c["module"] == "facemesh_fit"
    assert pv["requires"] == {"missing": [], "optional": [], "cycle": None}
    assert "_problems" not in pv
    assert nothing_written()


def test_the_panel_says_the_tier_written_as_tier(tmp_path):
    """MICRO-COR12 · ``tier`` and ``fascia`` are one key (SPEC.md §6.3): an
    envelope that writes ``tier`` (as the guide teaches) shows its tier in the
    Data panel, not «?»."""
    pkg = copy(MIXED, tmp_path)
    set_toml(pkg, r'^(\s*)fascia = ', r'\1tier = ', count=0)
    assert "fascia" not in (pkg / "em-extension.toml").read_text(encoding="utf-8")
    pv = X.preview(pkg)
    assert pv["ok"], pv["errors"]
    assert [v["fascia"] for v in pv["data"]["summary"]["vocabularies"]] == ["A", "A", "A"]


def test_the_code_panel_says_slots_and_panels(tmp_path):
    """MICRO-SEG08 · EMStudio's «Where you will find it» is computed from the
    preview before the code is installed: each command carries its slots (and
    whether it reads folders), the declarative panels their place."""
    pkg = copy(MIXED, tmp_path)
    with open(pkg / "em-extension.toml", "a", encoding="utf-8") as f:
        f.write('\n  [[code.panels]]\n  id = "pannello"\n  label = { en = "A panel", it = "Un pannello" }\n  place = "left"\n')
    c = X.preview(pkg)["code"]
    assert c["commands"][0]["slots"] == [{"name": "model", "kind": "id", "required": True}]
    assert "folders" not in c["commands"][0]
    assert c["panels"] == [{"id": "pannello", "label": {"en": "A panel", "it": "Un pannello"}, "place": "left"}]
    assert X.preview(MIXED)["code"]["panels"] == []


def test_archive_hash_is_the_same_for_a_folder_and_its_zip(tmp_path):
    assert X.preview(MIXED)["archive_hash"] == X.preview(zip_of(MIXED, tmp_path))["archive_hash"]


# ── install: three deliveries, one register ─────────────────────────────────

def test_install_everything_makes_three_deliveries_and_one_register():
    out = X.install(MIXED, trust=True)
    assert out["status"] == "installed" and not out["incomplete"]
    assert out["data"]["status"] == "installed" and out["code"]["status"] == "installed" and out["code"]["active"]
    # 1 · the vocabularies, to the manager, carried by the package
    vs = {v["scheme"]: v for v in V.vocab_installed()}
    assert len(vs) == 3 and all(v["carriers"] == [f"extension:{ID}"] for v in vs.values())
    # 2 · the rest of the data, without the .ttl the manager took
    folder = P.profiles_dir() / ID / "0.1.0"
    assert (folder / "profile.json").is_file() and not list(folder.rglob("*.ttl"))
    assert not list(folder.rglob("*.py"))
    # 3 · the code, in plugins/<source>/<id>/<code version>/, without the data
    code = plugin_folder()
    assert (code / "facemesh_fit" / "__init__.py").is_file() and not (code / "profile.json").exists()
    meta = json.loads((code / ".install.json").read_text())
    assert meta["module"] == "facemesh_fit" and meta["verified"] is False and meta["package"] == ID
    # the register ties them
    r = row()
    assert r["kind"] == "mixed" and r["source"] == "disk" and r["archive_hash"].startswith("sha256:")
    assert r["data"]["path"] == f"profiles/{ID}/0.1.0" and r["code"]["path"] == f"plugins/disk/{ID}/0.1.0"
    assert r["code"]["trusted"]["capabilities"] == ["ingest-batch", "read-graph"]
    # active, by host
    act = X.active_code("emstudio")
    assert [a["id"] for a in act] == [ID] and Path(act[0]["folder"]) == code
    assert X.active_code("blender") == []


def test_install_from_a_zip_and_from_bytes(tmp_path):
    z = zip_of(MIXED, tmp_path)
    assert X.install(z, trust=True)["code"]["status"] == "installed"
    assert X.install(z.read_bytes(), trust=True)["code"]["status"] == "unchanged"


def test_install_again_changes_nothing():
    X.install(MIXED, trust=True)
    out = X.install(MIXED)  # trust already given for the same permissions
    assert out["data"]["status"] == "unchanged" and out["code"]["status"] == "unchanged"


# ── the code falls alone ────────────────────────────────────────────────────

def test_without_trust_the_data_go_in_and_the_code_waits():
    out = X.install(MIXED)
    assert out["status"] == "data_only" and out["data"]["status"] == "installed"
    assert out["code"]["reason"]["code"] == "code_trust_required"
    assert "domanda di fiducia" in out["code"]["reason"]["it"]
    assert not plugin_folder().exists() and X.active_code() == []
    assert row()["code"]["status"] == "not_installed"
    # later, from the same window: the code alone, with its question
    later = X.install_code(ID, trust=True)
    assert later["code"]["status"] == "installed" and later["data"]["status"] == "unchanged"
    assert plugin_folder().is_dir()


def test_data_only_is_the_users_choice():
    out = X.install(MIXED, parts="data", trust=True)
    assert out["code"]["reason"]["code"] == "code_user_choice"
    assert out["code"]["reason"]["it"] == "codice non installato: scelta dell'utente (solo i dati)"
    assert not (X.plugins_dir() / "disk").exists()
    assert row()["code"]["installable_from"] == str(MIXED)


def test_code_for_another_platform_falls_and_the_data_stay():
    out = X.install(MIXED, trust=True, platform_name="linux-riscv64")
    assert out["data"]["status"] == "installed" and out["code"]["reason"]["code"] == "code_invalid"
    assert "linux-riscv64" in out["code"]["reason"]["en"]
    assert row()["code"]["status"] == "not_installed" and P.installed()


def test_a_wheel_missing_or_not_for_this_platform(tmp_path):
    pkg = copy(MIXED, tmp_path)
    set_toml(pkg, r'^(platforms = .*)$', r'\1\nwheels = ["./wheels/numpy-2.1.0-cp311-cp311-macosx_11_0_arm64.whl"]')
    pv = X.preview(pkg, platform_name="macos-arm64")
    # W19: the validator also says that windows-x64 and linux-x64 are declared with no numpy wheel
    assert [e["code"] for e in pv["code"]["errors"]] == ["code_wheel_missing"] + ["code_platform_wheel"] * 2
    assert pv["data"]["installable"]
    (pkg / "code" / "wheels").mkdir()
    (pkg / "code" / "wheels" / "numpy-2.1.0-cp311-cp311-macosx_11_0_arm64.whl").write_bytes(b"PK")
    assert [e["code"] for e in X.preview(pkg, platform_name="macos-arm64")["code"]["errors"]] == ["code_platform_wheel"] * 2
    set_toml(pkg, r'^platforms = .*$', 'platforms = ["macos-arm64"]')
    assert X.preview(pkg, platform_name="macos-arm64")["code"]["errors"] == []
    set_toml(pkg, r'^platforms = .*$', 'platforms = ["macos-arm64", "windows-x64"]')
    out = X.install(pkg, trust=True, platform_name="windows-x64")
    assert out["code"]["reason"]["code"] == "code_invalid"
    assert "no wheel of numpy for windows-x64" in out["code"]["reason"]["en"]


@pytest.mark.parametrize("name,plats", [
    ("numpy-2.1.0-cp311-cp311-macosx_11_0_arm64.whl", {"macos-arm64"}),
    ("numpy-2.1.0-cp311-cp311-macosx_10_9_universal2.whl", {"macos-arm64", "macos-x64"}),
    ("numpy-2.1.0-cp311-cp311-win_amd64.whl", {"windows-x64"}),
    ("numpy-2.1.0-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", {"linux-x64"}),
    ("numpy-2.1.0-cp311-cp311-manylinux_2_17_aarch64.whl", {"linux-arm64"}),
    ("attrs-24.2.0-py3-none-any.whl", None),
])
def test_wheel_platforms(name, plats):
    assert X.wheel_platforms(name) == plats


def test_this_platform_has_the_names_of_platforms():
    assert re.match(r"^(macos|windows|linux)-\w+$", X.this_platform())


# ── the data fall: nothing is installed ─────────────────────────────────────

def test_data_with_errors_install_nothing(tmp_path):
    pkg = copy(MIXED, tmp_path)
    prof = pkg / "data" / "profile.json"
    doc = json.loads(prof.read_text())
    doc["prefix"] = "Not A Prefix"
    prof.write_text(json.dumps(doc))
    with pytest.raises(X.ExtensionError) as e:
        X.install(pkg, trust=True)
    assert "prefix_bad" in e.value.report.codes()
    assert nothing_written()


def test_code_in_the_data_section_refuses_the_whole_archive(tmp_path):
    pkg = copy(MIXED, tmp_path)
    (pkg / "data" / "hook.py").write_text("print('no')")
    with pytest.raises(X.ExtensionError) as e:
        X.install(pkg, parts="data")
    assert "partition_code_in_data" in e.value.report.codes() and nothing_written()


def test_a_bad_code_section_lets_the_data_in(tmp_path):
    pkg = copy(MIXED, tmp_path)
    set_toml(pkg, r'^(\s*)files = .*$', r'\1files = "Legge le texture."')
    out = X.install(pkg, trust=True)
    assert out["data"]["status"] == "installed"
    assert out["code"]["reason"]["code"] == "code_invalid"
    assert out["code"]["reason"]["detail"][0]["code"] == "permission_reason"


def test_a_plugin_alone_with_errors_or_without_trust(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    set_toml(pkg, r'^entry = .*$', 'entry = "nothing"')
    with pytest.raises(X.ExtensionError) as e:
        X.install(pkg, trust=True)
    assert e.value.report.codes() == ["code_entry"]
    out = X.install(PLUGIN)
    assert out["status"] == "not_installed" and out["code"]["reason"]["code"] == "code_trust_required"
    assert nothing_written()


# ── requires: incomplete, offers, cycles ────────────────────────────────────

def test_separate_form_plugin_first_is_incomplete_then_complete():
    out = X.install(PLUGIN, trust=True)
    assert out["incomplete"] and out["code"]["status"] == "installed"
    miss = out["requires"]["missing"][0]
    assert miss["code"] == "requires_missing_data" and miss["it"] == "incompleto: mancano i dati di esempio-statuaria ^0.1"
    X.install(SEPARATE)
    rows = {r["id"]: r for r in X.installed()}
    assert not rows["facemesh_fit"]["incomplete"]
    assert rows[ID]["requires_optional"] == []  # the optional plugin is there


def test_the_optional_plugin_is_offered():
    out = X.install(SEPARATE)
    assert not out["incomplete"] and out["kind"] == "community-package"
    offer = out["requires"]["optional"][0]
    assert offer["code"] == "requires_optional" and "facemesh_fit" in offer["it"]
    assert out["code"]["status"] == "absent"


def test_a_data_package_installed_by_the_profile_library_satisfies_a_plugin():
    P.install(SEPARATE)
    out = X.install(PLUGIN, trust=True)
    assert not out["incomplete"]
    assert {r["id"]: r["registered"] for r in X.installed()} == {"facemesh_fit": True, ID: False}


def test_a_missing_vocabulary_is_said(tmp_path):
    pkg = copy(PLUGIN, tmp_path)
    set_toml(pkg, r'^\[requires\]$', '[requires]\nvocabularies = [{ scheme = "https://example.org/nope/", version = "^1.0" }]')
    out = X.install(pkg, trust=True)
    assert [m["code"] for m in out["requires"]["missing"]] == ["requires_missing_data", "requires_missing_vocabulary"]


def test_a_mandatory_cycle_is_refused_an_optional_one_is_not(tmp_path):
    # the SPEC's own example: statuaria ⇄ facemesh_fit, one side optional — not a cycle
    X.install(SEPARATE)
    X.install(PLUGIN, trust=True)
    a = copy(PLUGIN, tmp_path, "a")
    set_toml(a, r'^id = .*$', 'id = "ciclo-a"')
    set_toml(a, r'^extensions = .*$', 'extensions = [{ id = "ciclo-b", version = "^0.1", part = "code" , optional = false }]')
    set_toml(a, r'^entry = .*$', 'entry = "ciclo_a:plugin"')
    b = copy(PLUGIN, tmp_path, "b")
    set_toml(b, r'^id = .*$', 'id = "ciclo-b"')
    set_toml(b, r'^extensions = .*$', 'extensions = [{ id = "ciclo-a", version = "^0.2", part = "any" }]')
    set_toml(b, r'^entry = .*$', 'entry = "ciclo_b:plugin"')
    # a dependency on code must be optional: the validator refuses a mandatory one, so a → b goes through `any`
    set_toml(a, r'part = "code" , optional = false', 'part = "any"')
    X.install(a, trust=True)
    with pytest.raises(X.ExtensionError) as e:
        X.install(b, trust=True)
    assert e.value.report.codes() == ["requires_cycle"]
    assert "ciclo-b → ciclo-a → ciclo-b" in str(e.value)
    assert X.preview(b)["requires"]["cycle"] == ["ciclo-b", "ciclo-a", "ciclo-b"]


# ── update by section ───────────────────────────────────────────────────────

def test_update_only_the_code(tmp_path):
    X.install(MIXED, trust=True)
    new = copy(MIXED, tmp_path)
    bump(new, archive="0.1.1", code="0.2.0")
    pv = X.preview(new)
    assert pv["data"]["update"] == "unchanged" and pv["code"]["update"] == "new_version"
    assert pv["code"]["trust_needed"] is False  # same permissions, capabilities, source
    out = X.update(new)
    assert out["data"]["status"] == "unchanged" and out["code"]["status"] == "installed"
    assert {"code": "code_updated", "en": "code updated 0.1.0 → 0.2.0"}.items() <= \
        next(w for w in out["warnings"] if w["code"] == "code_updated").items()
    assert plugin_folder(version="0.1.0").is_dir() and plugin_folder(version="0.2.0").is_dir()
    assert [a["version"] for a in X.active_code()] == ["0.2.0"]
    assert row()["code"]["versions"] == ["0.1.0", "0.2.0"] and row()["version"] == "0.1.1"
    assert [r["version"] for r in P.installed()] == ["0.1.0"]


def test_new_permissions_ask_again_and_leave_the_old_code_active(tmp_path):
    X.install(MIXED, trust=True)
    new = copy(MIXED, tmp_path)
    bump(new, archive="0.2.0", code="0.3.0")
    set_toml(new, r'^(\s*)(files = .*)$', r'\1\2\n\1network = "Scarica il modello del volto"')
    pv = X.preview(new)
    assert pv["code"]["trust_needed"] and pv["code"]["trust_changes"] == ["permissions"]
    out = X.update(new)
    assert out["code"]["status"] == "not_installed" and out["code"]["reason"]["code"] == "code_trust_required"
    assert row()["code"]["status"] == "installed" and row()["code"]["version"] == "0.1.0"
    assert row()["code"]["pending"]["version"] == "0.3.0"
    assert [a["version"] for a in X.active_code()] == ["0.1.0"]
    assert X.install_code(ID, trust=True)["code"]["status"] == "installed"
    assert [a["version"] for a in X.active_code()] == ["0.3.0"]


def test_update_only_the_data_sits_beside(tmp_path):
    X.install(MIXED, trust=True)
    new = copy(MIXED, tmp_path)
    bump(new, archive="0.2.0", data="0.2.0")
    out = X.update(new)
    assert out["data"]["status"] == "installed" and out["code"]["status"] == "unchanged"
    assert any(w["code"] == "data_beside" for w in out["warnings"])
    assert sorted(r["version"] for r in P.installed()) == ["0.1.0", "0.2.0"]
    assert row()["data"]["versions"] == ["0.1.0", "0.2.0"] and row()["code"]["version"] == "0.1.0"


def test_a_section_version_is_not_reused(tmp_path):
    X.install(MIXED, trust=True)
    code_changed = copy(MIXED, tmp_path, "c")
    bump(code_changed, archive="0.1.1")
    init = code_changed / "code" / "facemesh_fit" / "__init__.py"
    init.write_text(init.read_text() + "\n# changed, same version\n")
    out = X.update(code_changed)
    assert out["code"]["reason"]["code"] == "code_invalid"
    assert [d["code"] for d in out["code"]["reason"]["detail"]] == ["code_version_reused"]
    assert row()["code"]["status"] == "installed"
    data_changed = copy(MIXED, tmp_path, "d")
    (data_changed / "data" / "help" / "en" / "index.md").write_text("changed, same version")
    with pytest.raises(X.ExtensionError) as e:
        X.update(data_changed)
    assert e.value.report.codes() == ["version_reused"]


def test_update_needs_an_installed_package():
    with pytest.raises(X.ExtensionError) as e:
        X.update(MIXED, trust=True)
    assert e.value.report.problems[0].text("it") == "esempio-statuaria non è installato"


# ── the three removals; the vocabularies stay ───────────────────────────────

def test_remove_the_code_keeps_the_data():
    X.install(MIXED, trust=True)
    plan = X.removal_plan(ID)
    assert plan["code"] == {"versions": ["0.1.0"]} and plan["data"]["removes_code"]
    assert len(plan["vocabularies_only_here"]) == 3
    out = X.remove_code(ID)
    assert out["code_removed"] == ["0.1.0"]
    assert not (X.plugins_dir() / "disk" / ID).exists() and X.active_code() == []
    r = row()
    assert r["data"]["status"] == "installed" and r["code"]["reason"]["code"] == "code_removed"
    assert P.installed() and len(V.vocab_installed()) == 3


def test_remove_the_data_removes_the_code_and_releases_the_vocabularies():
    X.install(MIXED, trust=True)
    out = X.remove_data(ID)
    assert out["code_removed"] == ["0.1.0"] and out["data_removed"] == ["0.1.0"]
    assert row() is None and not P.installed() and not (X.plugins_dir() / "disk" / ID).exists()
    vs = V.vocab_installed()
    assert len(vs) == 3 and all(v["orphan"] and v["removed_carriers"] == [f"extension:{ID}"] for v in vs)
    assert len(out["vocabularies"]["orphaned"]) == 3


def test_remove_the_package_with_the_box_ticked():
    X.install(MIXED, trust=True)
    out = X.remove(ID, purge_vocabularies=True)
    assert len(out["vocabularies"]["removed"]) == 3 and V.vocab_installed() == []
    assert nothing_written() or X.read_register()["extensions"] == {}


def test_remove_one_data_version_keeps_the_code(tmp_path):
    X.install(MIXED, trust=True)
    new = copy(MIXED, tmp_path)
    bump(new, archive="0.2.0", data="0.2.0")
    X.update(new)
    out = X.remove_data(ID, version="0.1.0")
    assert out["data_removed"] == ["0.1.0"] and out["code_removed"] == [] and out["vocabularies"] is None
    assert row()["data"]["versions"] == ["0.2.0"] and row()["code"]["status"] == "installed"


def test_data_another_package_requires_ask_for_confirmation():
    X.install(SEPARATE)
    X.install(PLUGIN, trust=True)
    assert X.removal_plan(ID)["data"]["required_by"] == ["facemesh_fit"]
    with pytest.raises(X.ExtensionError) as e:
        X.remove(ID)
    assert e.value.report.problems[0].text("it") == \
        "i dati di esempio-statuaria sono richiesti da facemesh_fit: conferma per rimuoverli"
    X.remove(ID, confirm=True)
    rows = {r["id"]: r for r in X.installed()}
    assert list(rows) == ["facemesh_fit"] and rows["facemesh_fit"]["incomplete"]


def test_removing_a_plugin_leaves_no_row():
    X.install(PLUGIN, trust=True)
    X.remove("facemesh_fit")
    assert X.read_register()["extensions"] == {} and X.read_enabled()["plugins"] == {}


# ── two archives, one module ────────────────────────────────────────────────

def test_the_same_module_from_two_archives_is_refused_at_activation():
    X.install(MIXED, trust=True)
    out = X.install(PLUGIN, trust=True)
    assert out["code"]["status"] == "installed" and out["code"]["active"] is False
    clash = out["code"]["inactive_reason"]
    assert clash["code"] == "module_collision"
    assert clash["it"] == "il modulo facemesh_fit è già caricato da esempio-statuaria 0.1.0: disattivalo prima"
    assert [a["id"] for a in X.active_code()] == [ID]
    with pytest.raises(X.ExtensionError):
        X.enable("facemesh_fit")
    X.disable(ID)
    X.enable("facemesh_fit")
    assert [a["id"] for a in X.active_code()] == ["facemesh_fit"]


# ── the command line ────────────────────────────────────────────────────────

def test_command_line(capsys):
    assert cli.main(["install", str(MIXED), "--data-only"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "data_only"
    assert cli.main(["list"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == ID
    assert cli.main(["--lang", "it", "remove", "nope"]) == 1
    assert "nope non è installato" in capsys.readouterr().err
    assert cli.main(["remove", ID]) == 0
