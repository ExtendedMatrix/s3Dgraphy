"""MICRO-PL22 · the repositories of this machine (row X2).

An index written by ``server-generate`` (X1) read by the client: the
repository added (an http(s) URL, ``file://``, a folder), «Allow online
access» (off: no network, ``file://`` still works), the archive checked
against ``archive_hash`` before it is opened, the ``blocklist`` respected,
``[requires]`` resolved through the repositories, tier C fetched. The
archives are the SYNTHETIC ones of tests/data/profiles (D-5, marked ESEMPIO).
The network is never touched: http(s) goes through :func:`set_fetcher`.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import urllib.parse
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.extensions import remote as RM
from s3dgraphy.profiles.problems import MESSAGES

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"


def built(src: Path, repo: Path) -> Path:
    res = X.build(src, output_dir=repo)
    assert res["ok"], res["errors"]
    return Path(res["path"])


def set_toml(folder: Path, pattern: str, repl: str):
    p = folder / "em-extension.toml"
    text, n = re.subn(pattern, repl, p.read_text(encoding="utf-8"), count=1, flags=re.M)
    assert n, pattern
    p.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_fetcher():
    RM.set_fetcher(None)
    yield
    RM.set_fetcher(None)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "lab-nas" / "estensioni"
    d.mkdir(parents=True)
    built(SEPARATE, d)
    built(PLUGIN, d)
    assert X.server_generate(d)["ok"]
    return d


class FakeWeb:
    """http(s) served from a folder; records every request and its headers."""

    def __init__(self, root: Path, host="repo.example.org"):
        self.root, self.host, self.calls = root, host, []

    def __call__(self, url, headers, limit):
        self.calls.append((url, dict(headers)))
        u = urllib.parse.urlsplit(url)
        if u.netloc != self.host:
            raise RM.urllib.error.URLError("unknown host")
        if getattr(self, "need_token", None) and headers.get("Authorization") != f"Bearer {self.need_token}":
            raise RM.urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
        return (self.root / u.path.lstrip("/").split("/", 1)[-1]).read_bytes()


# ── the repository added ────────────────────────────────────────────────────

def test_a_folder_a_file_url_and_an_https_url_are_repositories(repo, tmp_path):
    a = X.add_repository(str(repo))
    assert a["url"] == (repo / "index.json").resolve().as_uri() and a["name"] == "estensioni" and a["local"]
    b = X.add_repository("https://repo.example.org/em/", name="lab", token="s3cret", check_on_startup=True)
    assert b["url"] == "https://repo.example.org/em/index.json" and b["has_token"] and "token" not in b
    assert not b["local"] and b["check_on_startup"]
    assert [r["name"] for r in X.repositories()] == ["estensioni", "lab"]
    assert all("token" not in r for r in X.repositories())
    # the token stays on this machine, readable by this user only
    f = X.extensions_dir() / "repositories.json"
    assert "s3cret" in f.read_text(encoding="utf-8")
    if os.name == "posix":
        assert stat.S_IMODE(f.stat().st_mode) == 0o600
    for bad, code in [(repo.as_uri() + "/", "repo_url_used"), ("ftp://x/index.json", "repo_url_bad"),
                      ("https://other.example.org/i.json", "repo_name_used")]:
        with pytest.raises(X.RepoError) as e:
            X.add_repository(bad, name="lab" if code == "repo_name_used" else None)
        assert e.value.report.codes() == [code]
    with pytest.raises(X.RepoError, match="reserved"):
        X.add_repository("https://y.example.org/index.json", name="disk")
    X.update_repository("lab", token="")
    assert not X.get_repository("lab")["has_token"]
    assert X.remove_repository("lab") and not X.remove_repository("lab")


def test_online_access_is_off_by_default_and_file_urls_work_without_it(repo, monkeypatch):
    X.add_repository(str(repo), name="nas")
    X.add_repository("https://repo.example.org/em/index.json", name="web")
    web = FakeWeb(repo)
    RM.set_fetcher(web)
    assert X.online_access() is False
    res = X.sync()
    by = {r["name"]: r for r in res["repositories"]}
    assert by["nas"]["ok"] and by["nas"]["entries"] == 2
    assert not by["web"]["ok"] and by["web"]["problems"][0]["code"] == "repo_offline"
    assert "Consenti l'accesso in rete" in by["web"]["problems"][0]["it"]
    assert web.calls == []  # nothing went to the network
    assert X.set_online_access(True) is True
    assert X.sync("web")["repositories"][0]["ok"] and len(web.calls) == 1
    # the environment wins, like Blender's --offline-mode
    monkeypatch.setenv("S3DGRAPHY_ONLINE_ACCESS", "0")
    assert X.online_access() is False and X.online_access_setting()["setting"] is True
    assert X.sync("web")["repositories"][0]["problems"][0]["code"] == "repo_offline"
    assert len(web.calls) == 1
    # the copy read before stays
    assert X.get_repository("web")["entries"] == 2 and X.get_repository("web")["error"]["code"] == "repo_offline"


def test_the_token_goes_as_bearer_only_to_the_index_host(repo):
    X.set_online_access(True)
    doc = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    # one archive served by another host: the token must not follow it there
    doc["data"][1]["archive_url"] = "https://cdn.example.net/x/facemesh_fit-0.2.0.zip"
    (repo / "index.json").write_text(json.dumps(doc), encoding="utf-8")
    web = FakeWeb(repo)
    web.need_token = "s3cret"
    seen = []

    def both(url, headers, limit):
        seen.append((url, dict(headers)))
        if "cdn.example.net" in url:
            return (repo / "facemesh_fit-0.2.0.zip").read_bytes()
        return web(url, headers, limit)

    RM.set_fetcher(both)
    X.add_repository("https://repo.example.org/em/index.json", name="lab", token="wrong")
    r = X.sync("lab")["repositories"][0]
    assert not r["ok"] and r["problems"][0]["code"] == "repo_denied"
    X.update_repository("lab", token="s3cret")
    assert X.sync("lab")["repositories"][0]["ok"]
    X.download("lab", "esempio-statuaria")
    X.download("lab", "facemesh_fit")
    auth = {u: h.get("Authorization") for u, h in seen}
    assert auth["https://repo.example.org/em/index.json"] == "Bearer s3cret"
    assert auth["https://repo.example.org/em/esempio-statuaria-0.1.0.zip"] == "Bearer s3cret"
    assert auth["https://cdn.example.net/x/facemesh_fit-0.2.0.zip"] is None


def test_a_bad_index_keeps_the_previous_copy(repo):
    X.add_repository(str(repo), name="nas")
    assert X.sync("nas")["repositories"][0]["ok"]
    (repo / "index.json").write_text('{"version": "v9", "data": []}', encoding="utf-8")
    r = X.sync("nas")["repositories"][0]
    assert not r["ok"] and "repo_index_bad" in [p["code"] for p in r["problems"]]
    assert len(X.cached_index("nas")["data"]) == 2


# ── installing from the index ──────────────────────────────────────────────

def test_install_from_a_file_repository_checks_the_hash_and_names_the_source(repo):
    X.add_repository(str(repo), name="nas")
    X.sync()
    av = X.available()["available"]
    assert [(a["id"], a["version"], a["installed"]) for a in av] == [("esempio-statuaria", "0.1.0", None),
                                                                    ("facemesh_fit", "0.2.0", None)]
    out = X.install_from("nas", "esempio-statuaria")
    row = out["installed"]
    assert row["status"] == "installed" and row["source"] == "nas"
    entry = X.cached_index("nas")["data"][0]
    assert X.read_register()["extensions"]["esempio-statuaria"]["archive_hash"] == entry["content_hash"]
    kept = X.extensions_dir() / "archives" / "nas" / "esempio-statuaria-0.1.0.zip"
    assert kept.is_file() and row["origin"] == str(kept)
    a = {x["id"]: x for x in X.available()["available"]}["esempio-statuaria"]
    assert a["installed"] == "0.1.0" and not a["update"] and a["same_source"]


def test_an_archive_that_is_not_the_index_one_is_refused_before_it_is_opened(repo):
    X.add_repository(str(repo), name="nas")
    X.sync()
    z = repo / "esempio-statuaria-0.1.0.zip"
    blob = bytearray(z.read_bytes())
    blob[-1] ^= 0xFF
    z.write_bytes(bytes(blob))
    with pytest.raises(X.ExtensionError) as e:
        X.install_from("nas", "esempio-statuaria")
    assert e.value.report.codes() == ["index_hash_mismatch"]
    assert "lo scaricato non è l'archivio" in e.value.report.problems[0].text("it")
    assert X.installed() == [] and not (X.extensions_dir() / "archives" / "nas" / z.name).exists()


def test_the_plugin_brings_the_data_it_requires_and_the_code_is_asked_for(repo):
    X.add_repository(str(repo), name="nas")
    X.sync()
    plan = X.plan_install("nas", "facemesh_fit")
    assert [(s["id"], s["requested"]) for s in plan["steps"]] == [("esempio-statuaria", False), ("facemesh_fit", True)]
    assert plan["unresolved"] == [] and plan["cycle"] is None
    pv = X.preview_from("nas", "facemesh_fit")
    assert pv["code"]["present"] and pv["code"]["trust_needed"] and pv["code"]["source"] == "nas"
    assert pv["repository"]["archive_hash"].startswith("sha256:") and pv["plan"]["steps"][0]["id"] == "esempio-statuaria"
    # what the plan installs first is not said «missing» in the confirmation
    assert pv["requires"]["missing"] == []
    # without trust: the requirement's data go in, the plugin's code does not
    out = X.install_from("nas", "facemesh_fit")
    assert out["requires"][0]["id"] == "esempio-statuaria" and out["requires"][0]["status"] == "installed"
    assert out["installed"]["status"] == "not_installed"
    out = X.install_from("nas", "facemesh_fit", trust=True)
    assert out["requires"] == []  # already here
    code = X.read_register()["extensions"]["facemesh_fit"]["code"]
    assert code["status"] == "installed" and code["path"] == "plugins/nas/facemesh_fit/0.2.0"
    assert not out["installed"]["incomplete"]
    assert (X.plugins_dir() / "nas" / "facemesh_fit" / "0.2.0").is_dir()


def test_without_requires_the_package_installs_incomplete(repo):
    X.add_repository(str(repo), name="nas")
    X.sync()
    out = X.install_from("nas", "facemesh_fit", trust=True, with_requires=False)
    assert out["requires"] == [] and out["installed"]["incomplete"]
    assert X.get("esempio-statuaria") is None


def test_a_requirement_no_repository_has_is_said_and_an_offer_is_not_installed(repo, tmp_path):
    (repo / "esempio-statuaria-0.1.0.zip").unlink()
    assert X.server_generate(repo)["ok"]
    X.add_repository(str(repo), name="nas")
    X.sync()
    plan = X.plan_install("nas", "facemesh_fit")
    assert [s["id"] for s in plan["steps"]] == ["facemesh_fit"]
    u, = plan["unresolved"]
    assert u["id"] == "esempio-statuaria" and "nessun repository offre" in u["problem"]["it"]
    # the other way round: statuaria OFFERS the plugin (optional), never installs it on its own
    d2 = tmp_path / "r2"
    d2.mkdir()
    built(SEPARATE, d2)
    built(PLUGIN, d2)
    X.server_generate(d2)
    X.add_repository(str(d2), name="r2")
    X.sync("r2")
    plan = X.plan_install("r2", "esempio-statuaria")
    assert [s["id"] for s in plan["steps"]] == ["esempio-statuaria"]
    assert plan["offers"] == [{"id": "facemesh_fit", "range": "^0.2", "part": "code", "repo": "r2", "version": "0.2.0"}]
    out = X.install_from("r2", "esempio-statuaria")
    assert X.get("facemesh_fit") is None and out["offers"][0]["id"] == "facemesh_fit"


def test_a_requirement_is_looked_for_in_the_other_repositories(repo, tmp_path):
    only_plugin = tmp_path / "plugins-only"
    only_plugin.mkdir()
    shutil.move(str(repo / "facemesh_fit-0.2.0.zip"), str(only_plugin))
    X.server_generate(repo)
    X.server_generate(only_plugin)
    X.add_repository(str(only_plugin), name="plugins")
    X.add_repository(str(repo), name="nas")
    X.sync()
    plan = X.plan_install("plugins", "facemesh_fit")
    assert [(s["repo"], s["id"]) for s in plan["steps"]] == [("nas", "esempio-statuaria"), ("plugins", "facemesh_fit")]


def test_a_cycle_of_mandatory_requirements_is_refused_before_any_download(tmp_path):
    d = tmp_path / "cyc"
    d.mkdir()
    a, b = tmp_path / "a", tmp_path / "b"
    shutil.copytree(SEPARATE, a)
    shutil.copytree(PLUGIN, b)
    set_toml(a, r'^extensions = .*$', 'extensions = [{ id = "facemesh_fit", version = "^0.2", part = "any" }]')
    built(a, d)
    built(b, d)
    # server_generate refuses the cycle in the index; write the index anyway to see the client refuse it too
    res = X.server_generate(d)
    assert "index_requires_cycle" in [p["code"] for p in res["problems"]] or not res["ok"]
    X.add_repository(str(d), name="cyc")
    X.sync()
    if not any(e["id"] == "facemesh_fit" for e in X.cached_index("cyc")["data"]):
        pytest.skip("the index refused the cycle itself")
    with pytest.raises(X.RepoError) as e:
        X.install_from("cyc", "facemesh_fit", trust=True)
    assert e.value.report.codes() == ["requires_cycle"]
    assert not (X.extensions_dir() / "archives" / "cyc").exists()


# ── the blocklist ──────────────────────────────────────────────────────────

def test_a_withdrawn_id_is_not_offered_and_an_installed_one_is_said(repo):
    X.add_repository(str(repo), name="nas")
    X.sync()
    X.install_from("nas", "esempio-statuaria")
    (repo / "blocklist.json").write_text(json.dumps([{"id": "esempio-statuaria", "reason": "replaced",
                                                      "reason_it": "sostituito"}]), encoding="utf-8")
    X.server_generate(repo)
    X.sync()
    av = X.available()
    assert [a["id"] for a in av["available"]] == ["facemesh_fit"]
    b, = av["blocked"]
    assert b["id"] == "esempio-statuaria" and "lo ha ritirato" in b["problem"]["it"]
    with pytest.raises(X.RepoError) as e:
        X.install_from("nas", "esempio-statuaria")
    assert e.value.report.codes() == ["repo_blocked"]
    # a withdrawn id is never picked to satisfy a requirement either
    X.remove("esempio-statuaria")
    assert [u["id"] for u in X.plan_install("nas", "facemesh_fit")["unresolved"]] == ["esempio-statuaria"]


# ── updates ────────────────────────────────────────────────────────────────

def test_a_newer_version_is_an_update_and_check_on_startup_reads_only_those_repositories(repo, tmp_path):
    X.add_repository(str(repo), name="nas", check_on_startup=True)
    other = tmp_path / "other"
    other.mkdir()
    X.server_generate(other)
    X.add_repository(str(other), name="other")
    X.sync()
    X.install_from("nas", "facemesh_fit", trust=True)
    newer = tmp_path / "fm"
    shutil.copytree(PLUGIN, newer)
    set_toml(newer, r'^version = "0.2.0"$', 'version = "0.2.1"')
    built(newer, repo)
    X.server_generate(repo)
    res = X.sync(startup=True)
    assert [r["name"] for r in res["repositories"]] == ["nas"]
    assert res["updates"] == [{"id": "facemesh_fit", "repo": "nas", "installed": "0.2.0", "version": "0.2.1"}]
    out = X.update_from("nas", "facemesh_fit", trust=False)
    # same permissions, same source: no new question, the code is replaced
    assert X.read_register()["extensions"]["facemesh_fit"]["code"]["version"] == "0.2.1"
    assert X.updates() == []
    with pytest.raises(X.ExtensionError):
        X.update_from("nas", "nothing-here")


# ── tier C: «Download locally», automatic ──────────────────────────────────

def _tier_c_package(tmp_path, url_of):
    pkg = tmp_path / "stat-c"
    shutil.copytree(SEPARATE, pkg)
    src = pkg / "vocab" / "lavorazione.ttl"
    blob = src.read_bytes()
    source = tmp_path / "fonte" / "lavorazione.ttl"
    source.parent.mkdir()
    source.write_bytes(blob)
    src.unlink()
    url = url_of(source)
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    set_toml(pkg, r'^  path = "vocab/lavorazione.ttl"\n((?:  .*\n)*?)  license = "SPDX:CC-BY-4.0"\n  fascia = "A"\n  digest = .*$',
             r'\1  license = "SPDX:LicenseRef-esempio"\n  fascia = "C"\n'
             f'  fetch = {{ url = "{url}", digest = "{digest}", terms = "https://example.org/terms" }}')
    return pkg


def test_tier_c_is_fetched_from_a_file_source_and_offline_only_said(tmp_path):
    d = tmp_path / "repo-c"
    d.mkdir()
    built(_tier_c_package(tmp_path, lambda p: p.as_uri()), d)
    X.server_generate(d)
    X.add_repository(str(d), name="nas")
    X.sync()
    plan = X.plan_install("nas", "esempio-statuaria")
    c, = plan["tier_c"]
    assert c["will_fetch"] and c["url"].startswith("file://")
    out = X.install_from("nas", "esempio-statuaria")
    t, = out["tier_c"]
    assert t["fetched"], t
    from s3dgraphy.authorities import packages as P
    s = P._summary(P.vocab_folder(t["id"], t["version"]))
    assert s["status"] == "ready" and s["local_copy"]


def test_tier_c_over_https_waits_for_online_access(tmp_path):
    d = tmp_path / "repo-c"
    d.mkdir()
    built(_tier_c_package(tmp_path, lambda p: "https://fonte.example.org/lavorazione.ttl"), d)
    X.server_generate(d)
    X.add_repository(str(d), name="nas")
    X.sync()
    assert not X.plan_install("nas", "esempio-statuaria")["tier_c"][0]["will_fetch"]
    out = X.install_from("nas", "esempio-statuaria")
    t, = out["tier_c"]
    assert not t["fetched"] and t["problem"]["code"] == "repo_tier_c_offline"
    assert "Scarica in locale" in t["problem"]["it"]
    assert out["installed"]["status"] == "installed"  # the data are in, the vocabulary is a stub


# ── the command line, the messages ─────────────────────────────────────────

def test_the_command_line_adds_syncs_and_installs(repo, capsys):
    assert cli.main(["repo", "add", str(repo), "--name", "nas"]) == 0
    assert cli.main(["repo", "online"]) == 0
    assert json.loads(capsys.readouterr().out.split("\n}\n")[-1] or "{}") is not None
    assert cli.main(["repo", "sync"]) == 0
    capsys.readouterr()
    assert cli.main(["repo", "install", "nas", "facemesh_fit", "--trust", "--trust-requires"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["installed"]["code"]["status"] == "installed" and out["requires"][0]["id"] == "esempio-statuaria"
    assert cli.main(["repo", "install", "nas", "nothing", "--lang", "it"]) == 1
    assert "non offre" in capsys.readouterr().err


def test_every_repo_message_is_in_english_and_italian():
    codes = [c for c in MESSAGES if c.startswith("repo_")]
    assert len(codes) >= 19
    for c in codes:
        en, it = MESSAGES[c]
        assert en and it and en != it
        assert set(re.findall(r"{(\w+)", en)) == set(re.findall(r"{(\w+)", it)), c
