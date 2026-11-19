"""MICRO-PL24 · the list of the reviewed (row X4).

A review is of the digest of the archive's CODE section (the data's for an
archive with no code), written in a repository's ``reviewed.json``, copied
into the index by ``server-generate``; a code reviewed in a repository whose
reviews count on this machine (``trust_reviews``: the official index by
default, any other once the person turns it on) installs without the trust
question and is ``verified``. A data-only update keeps the review; a change
of code loses it; a review withdrawn makes the code unverified again, still
installed. The archives are the SYNTHETIC ones of tests/data/profiles (D-5,
marked ESEMPIO); the network is never touched.
"""
import json
import re
import shutil
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.extensions import remote as RM
from s3dgraphy.extensions import review as RV
from s3dgraphy.profiles.problems import MESSAGES

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN, MIXED = DATA / "esempio-statuaria", DATA / "facemesh_fit", DATA / "esempio-statuaria-misto"
EDITOR = "@zalmoxes-laran"


def built(src: Path, repo: Path) -> Path:
    res = X.build(src, output_dir=repo)
    assert res["ok"], res["errors"]
    return Path(res["path"])


def sub(path: Path, pattern: str, repl: str):
    text, n = re.subn(pattern, repl, path.read_text(encoding="utf-8"), count=1, flags=re.M)
    assert n, pattern
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_fetcher():
    RM.set_fetcher(None)
    yield
    RM.set_fetcher(None)


@pytest.fixture
def repo(tmp_path):
    """A laboratory's folder: the statuary data and facemesh_fit, the plugin reviewed."""
    d = tmp_path / "lab"
    d.mkdir()
    built(SEPARATE, d)
    z = built(PLUGIN, d)
    got = X.add_review(d, z, by=EDITOR, on="2026-11-19", as_="editor", note="ESEMPIO")
    assert got["added"]
    assert X.server_generate(d)["ok"]
    return d


def code_meta(source: str, eid: str, version: str) -> dict:
    return json.loads((X.plugins_dir() / source / eid / version / ".install.json").read_text(encoding="utf-8"))


# ── the list ────────────────────────────────────────────────────────────────

def test_a_review_is_of_the_code_digest_and_is_written_once(tmp_path):
    z = built(PLUGIN, tmp_path)
    d = X.review_digest(z)
    assert d["section"] == "code" and d["digest"].startswith("sha256:")
    # the folder and its zip are the same code
    assert X.review_digest(PLUGIN)["digest"] == d["digest"]
    # a data-only archive is reviewed on its data
    assert X.review_digest(SEPARATE)["section"] == "data"
    a = X.add_review(tmp_path, z, by=EDITOR, on="2026-11-19", as_="editor")
    assert a["added"] and a["row"]["digest"] == d["digest"] and a["row"]["version"] == "0.2.0"
    b = X.add_review(tmp_path / "reviewed.json", PLUGIN, by=EDITOR, on="2026-11-20")
    assert not b["added"] and b["problem"]["code"] == "review_duplicate" and "2026-11-19" in b["problem"]["it"]
    X.add_review(tmp_path, z, by="@curatrice", on="2026-11-18", as_="curator:esempio-statuaria")
    rows = json.loads((tmp_path / "reviewed.json").read_text(encoding="utf-8"))["reviewed"]
    assert [r["on"] for r in rows] == ["2026-11-18", "2026-11-19"]   # a stable order
    with pytest.raises(X.ExtensionError) as e:
        X.add_review(tmp_path, z, by=" ")
    assert e.value.report.codes() == ["review_no_by"]


def test_the_index_carries_the_review_of_the_code_and_says_a_review_of_nothing(repo):
    idx = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    by = {e["id"]: e for e in idx["data"]}
    rv = by["facemesh_fit"]["reviewed"]
    assert rv == {"by": EDITOR, "on": "2026-11-19", "as": "editor", "note": "ESEMPIO",
                  "digest": by["facemesh_fit"]["sections"]["code"]["digest"]}
    assert "reviewed" not in by["esempio-statuaria"]
    rows = json.loads((repo / "reviewed.json").read_text(encoding="utf-8"))
    rows["reviewed"].append({"id": "facemesh_fit", "digest": "sha256:" + "0" * 64, "by": "@x", "on": "2026-01-01"})
    (repo / "reviewed.json").write_text(json.dumps(rows), encoding="utf-8")
    res = X.server_generate(repo)
    assert res["ok"]     # a warning, never a failure
    assert [p["code"] for p in res["problems"]] == ["index_review_unused"]


# ── whose reviews count ─────────────────────────────────────────────────────

def test_only_the_official_index_reviews_count_by_default(repo):
    lab = X.add_repository(str(repo), name="lab")
    off = X.add_repository(RM.OFFICIAL_URL, name="ufficiale")
    assert lab["trust_reviews"] is False and off["trust_reviews"] is True and off["official"]
    X.sync("lab")
    a = {x["id"]: x for x in X.available("lab")["available"]}
    assert a["facemesh_fit"]["reviewed"]["by"] == EDITOR and a["facemesh_fit"]["verified"] is False
    pv = X.preview_from("lab", "facemesh_fit")
    assert pv["code"]["trust_needed"] and not pv["code"]["verified"] and "reviewed" not in pv["code"]
    assert pv["repository"]["trust_reviews"] is False
    # the person turns the laboratory's reviews on
    assert X.update_repository("lab", trust_reviews=True)["trust_reviews"]
    assert X.trusted_repositories() == ["lab", "ufficiale"]
    a = {x["id"]: x for x in X.available("lab")["available"]}
    assert a["facemesh_fit"]["verified"] is True and a["esempio-statuaria"]["verified"] is False
    pv = X.preview_from("lab", "facemesh_fit")
    assert pv["code"]["trust_needed"] is False and pv["code"]["verified"] is True
    assert pv["code"]["reviewed"]["by"] == EDITOR and pv["code"]["reviewed"]["repo"] == "lab"
    assert "rivisto da @zalmoxes-laran il 2026-11-19 (lab)" in pv["code"]["review_note"]["it"]


def test_a_reviewed_plugin_installs_without_the_second_confirmation(repo):
    X.add_repository(str(repo), name="lab", trust_reviews=True)
    X.sync()
    out = X.install_from("lab", "facemesh_fit")          # no trust answer
    top = out["installed"]
    assert top["status"] == "installed" and top["code"]["status"] == "installed"
    assert top["code"]["verified"] is True and top["code"]["trusted_by"] == "review"
    assert any(w["code"] == "code_reviewed" for w in out["warnings"])
    row = X.read_register()["extensions"]["facemesh_fit"]["code"]
    assert row["verified"] and row["reviewed"]["by"] == EDITOR and row["reviewed"]["repo"] == "lab"
    meta = code_meta("lab", "facemesh_fit", "0.2.0")
    assert meta["verified"] is True and meta["reviewed"]["on"] == "2026-11-19"
    # what the plugins' loader reads, and so the DTC of its acts
    from s3dgraphy.em import plugins as P
    d = P.Plugin(id="facemesh_fit", version="0.2.0", source="lab",
                 folder=X.plugins_dir() / "lab" / "facemesh_fit" / "0.2.0", meta=meta).as_dict()
    assert d["verified"] is True and d["reviewed"]["by"] == EDITOR
    assert X.reviewed_installed() == [{"id": "facemesh_fit", "version": "0.2.0", "source": "lab", "verified": True,
                                       "reviewed": row["reviewed"], "trusted_by": "review",
                                       "digest": row["digest"]}]
    # the requirement had no code: nothing to review
    assert X.read_register()["extensions"]["esempio-statuaria"]["code"] == {"status": "absent"}


def test_the_same_code_from_disk_is_the_same_review(repo, tmp_path):
    X.add_repository(str(repo), name="lab", trust_reviews=True)
    X.sync()
    X.install_from("lab", "esempio-statuaria")
    z = built(PLUGIN, tmp_path / "scaricato")
    pv = X.preview(z)
    assert pv["source"] == "disk" and pv["code"]["verified"] and not pv["code"]["trust_needed"]
    out = X.install(z)
    assert out["code"]["status"] == "installed" and out["code"]["verified"]
    # «review=None»: a host that wants the question anyway
    X.remove("facemesh_fit")
    assert X.preview(z, review=None)["code"]["trust_needed"]


def test_a_data_only_update_keeps_the_review_and_a_code_change_loses_it(tmp_path):
    d = tmp_path / "lab"
    d.mkdir()
    z = built(MIXED, d)
    X.add_review(d, z, by="@curatrice", on="2026-11-19", as_="curator:esempio-statuaria")
    assert X.server_generate(d)["ok"]
    X.add_repository(str(d), name="lab", trust_reviews=True)
    X.sync()
    first = X.install_from("lab", "esempio-statuaria")["installed"]
    assert first["code"]["verified"] and first["code"]["trusted_by"] == "review"
    # 0.1.1: the data change, the code does not
    new = tmp_path / "misto-dati"
    shutil.copytree(MIXED, new)
    sub(new / "em-extension.toml", r'^version = "0.1.0"$', 'version = "0.1.1"')
    sub(new / "em-extension.toml", r'(\[data\]\n)version = "0.1.0"', r'\1version = "0.1.1"')
    sub(new / "data" / "profile.json", r'"version": "0.1.0"', '"version": "0.1.1"')
    sub(new / "data" / "examples" / "testa-esempio.em.json", r'"version": "0.1.0"', '"version": "0.1.1"')
    (new / "data" / "help" / "en" / "index.md").write_text("Example help, revised (ESEMPIO).\n", encoding="utf-8")
    built(new, d)
    assert X.server_generate(d)["ok"]
    idx = {(e["id"], e["version"]): e for e in json.loads((d / "index.json").read_text(encoding="utf-8"))["data"]}
    assert idx[("esempio-statuaria", "0.1.1")]["reviewed"]["by"] == "@curatrice"
    X.sync()
    ahead = X.check_updates(read=False)["updates"]
    assert ahead[0]["version"] == "0.1.1" and ahead[0]["verified"] and not ahead[0]["trust_needed"]
    res = X.update_all()
    assert [u["to"] for u in res["updated"]] == ["0.1.1"] and res["needs_trust"] == []
    assert X.read_register()["extensions"]["esempio-statuaria"]["code"]["verified"]
    # 0.1.2: the code changes — nobody has read it, and the person was never asked
    newer = tmp_path / "misto-codice"
    shutil.copytree(new, newer)
    sub(newer / "em-extension.toml", r'^version = "0.1.1"$', 'version = "0.1.2"')
    sub(newer / "em-extension.toml", r'(\[code\]\n)version = "0.1.0"', r'\1version = "0.1.1"')
    init = newer / "code" / "facemesh_fit" / "__init__.py"
    init.write_text(init.read_text(encoding="utf-8") + "\n# changed (ESEMPIO)\n", encoding="utf-8")
    built(newer, d)
    assert X.server_generate(d)["ok"]
    X.sync()
    ahead = X.check_updates(read=False)["updates"]
    assert ahead[0]["version"] == "0.1.2" and ahead[0]["trust_needed"] and not ahead[0]["verified"]
    res = X.update_all()
    assert res["updated"] == [] and res["needs_trust"][0]["id"] == "esempio-statuaria"
    res = X.update_all(trust=["esempio-statuaria"])
    code = X.read_register()["extensions"]["esempio-statuaria"]["code"]
    assert code["version"] == "0.1.1" and not code["verified"] and code["trusted_by"] == "person"
    # back to the reviewed code: no question, verified again
    back = X.use_code("esempio-statuaria", "0.1.0")
    assert back["verified"] and back["reviewed"]["by"] == "@curatrice"


def test_a_review_withdrawn_or_arrived_is_said_at_the_sync(repo, tmp_path):
    X.add_repository(str(repo), name="lab", trust_reviews=True)
    X.sync()
    X.install_from("lab", "facemesh_fit")
    (repo / "reviewed.json").write_text('{"reviewed": []}\n', encoding="utf-8")
    assert X.server_generate(repo)["ok"]
    res = X.sync()
    assert [w["id"] for w in res["reviews"]["withdrawn"]] == ["facemesh_fit"]
    assert "resta installato, non verificato" in res["reviews"]["withdrawn"][0]["problem"]["it"]
    row = X.read_register()["extensions"]["facemesh_fit"]["code"]
    assert row["status"] == "installed" and row.get("active") is not False and not row["verified"]
    assert code_meta("lab", "facemesh_fit", "0.2.0")["verified"] is False
    # the review comes back
    X.add_review(repo, PLUGIN, by=EDITOR, on="2026-11-21", as_="editor")
    X.server_generate(repo)
    res = X.sync()
    assert [w["id"] for w in res["reviews"]["verified"]] == ["facemesh_fit"]
    assert X.read_register()["extensions"]["facemesh_fit"]["code"]["reviewed"]["on"] == "2026-11-21"
    # the person stops trusting the laboratory's reviews
    out = X.update_repository("lab", trust_reviews=False)
    assert [w["id"] for w in out["reviews"]["withdrawn"]] == ["facemesh_fit"]
    # and removing a repository takes its reviews away too
    X.update_repository("lab", trust_reviews=True)
    assert X.read_register()["extensions"]["facemesh_fit"]["code"]["verified"]
    X.remove_repository("lab")
    assert not X.read_register()["extensions"]["facemesh_fit"]["code"]["verified"]


def test_a_withdrawn_id_and_development_code_are_never_reviewed(repo):
    X.add_repository(str(repo), name="lab", trust_reviews=True)
    X.sync()
    d = X.review_digest(PLUGIN)["digest"]
    assert RV.find_review("facemesh_fit", d)["repo"] == "lab"
    assert RV.review_for("facemesh_fit", d, "dev") is None
    assert RV.review_for("facemesh_fit", d, "disk", review={"digest": "sha256:" + "1" * 64, "by": "x", "on": "y"}) is None
    (repo / "blocklist.json").write_text(json.dumps([{"id": "facemesh_fit", "reason": "ESEMPIO"}]), encoding="utf-8")
    X.server_generate(repo)
    X.sync()
    assert RV.find_review("facemesh_fit", d) is None


def test_the_command_line_writes_and_lists_reviews(repo, tmp_path, capsys):
    z = built(PLUGIN, tmp_path / "z")
    assert cli.main(["review", "digest", str(z)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["id"] == "facemesh_fit" and out["section"] == "code"
    lst = tmp_path / "r" / "reviewed.json"
    assert cli.main(["review", "add", str(z), "--reviewed", str(lst), "--by", "@curatrice",
                     "--as", "curator:esempio-statuaria", "--on", "2026-11-19"]) == 0
    assert json.loads(capsys.readouterr().out)["added"]
    assert cli.main(["repo", "add", str(repo), "--name", "lab", "--trust-reviews"]) == 0
    assert json.loads(capsys.readouterr().out)["trust_reviews"] is True
    assert cli.main(["repo", "reviews", "lab", "off"]) == 0
    assert json.loads(capsys.readouterr().out)["trust_reviews"] is False
    assert cli.main(["review", "list"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert cli.main(["review", "add", str(z), "--lang", "it"]) == 1
    assert "chi l'ha rivisto" in capsys.readouterr().err


def test_every_review_message_is_in_english_and_italian():
    codes = [c for c in MESSAGES if c.startswith("review_") or c in ("code_reviewed", "index_review_unused")]
    assert len(codes) == 7
    for c in codes:
        en, it = MESSAGES[c]
        assert en and it and en != it
        assert set(re.findall(r"{(\w+)", en)) == set(re.findall(r"{(\w+)", it)), c
