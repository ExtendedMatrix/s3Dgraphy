"""MICRO-PL28 · the signature of a repository (row X8): minisign over archive_hash.

Ed25519 (RFC 8032) and minisign's files in pure Python; a ``.minisig`` beside
every archive the index lists (its trusted comment names id, version and
archive_hash) and beside the index. A repository added with public keys
takes only a signed index and opens only signed archives; an archive from
disk with a signature of a known key says «signed by», with another's bytes
is refused. The archives are the SYNTHETIC ones of tests/data/profiles (D-5,
marked ESEMPIO); the network is never touched.
"""
import base64
import json
import re
import shutil
from pathlib import Path

import pytest

from s3dgraphy import extensions as X
from s3dgraphy.extensions import __main__ as cli
from s3dgraphy.extensions import remote as RM
from s3dgraphy.extensions import signing as S
from s3dgraphy.profiles.problems import MESSAGES

DATA = Path(__file__).parent / "data" / "profiles"
SEPARATE, PLUGIN = DATA / "esempio-statuaria", DATA / "facemesh_fit"


def built(src: Path, repo: Path) -> Path:
    res = X.build(src, output_dir=repo)
    assert res["ok"], res["errors"]
    return Path(res["path"])


@pytest.fixture(autouse=True)
def _no_fetcher():
    RM.set_fetcher(None)
    yield
    RM.set_fetcher(None)


@pytest.fixture
def key(tmp_path):
    got = S.keygen(tmp_path / "keys" / "repo.key")
    return {"secret": tmp_path / "keys" / "repo.key", "public": Path(got["public"]), "id": got["key_id"],
            "b64": got["public_key"]}


@pytest.fixture
def repo(tmp_path, key):
    """A laboratory's folder, its index and its signatures."""
    d = tmp_path / "lab"
    d.mkdir()
    built(SEPARATE, d)
    built(PLUGIN, d)
    res = X.server_generate(d, sign_key=key["secret"])
    assert res["ok"] and res["signature"]["ok"], res["problems"]
    return d


def entry_file(repo: Path, eid: str) -> Path:
    idx = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    e = next(e for e in idx["data"] if e["id"] == eid)
    return repo / e["archive_url"].rsplit("/", 1)[-1]


# ── Ed25519 and minisign's files ────────────────────────────────────────────

def test_ed25519_is_rfc_8032():
    # RFC 8032 §7.1, TEST 1 and TEST 2
    for seed, pub, msg, sig in [
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
         "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
         "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")]:
        seed, pub, msg, sig = (bytes.fromhex(x) for x in (seed, pub, msg, sig))
        assert S.ed25519_public(seed) == pub
        assert S.ed25519_sign(seed, msg) == sig
        assert S.ed25519_verify(pub, msg, sig)
        assert not S.ed25519_verify(pub, msg + b"!", sig)
        bad = bytearray(sig)
        bad[63] ^= 0x10          # S >= L or simply wrong
        assert not S.ed25519_verify(pub, msg, bytes(bad))


def test_ed25519_agrees_with_cryptography_when_it_is_there():
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    import os
    for n in range(8):
        seed, msg = os.urandom(32), os.urandom(n * 37)
        k = ed.Ed25519PrivateKey.from_private_bytes(seed)
        assert S.ed25519_sign(seed, msg) == k.sign(msg)
        assert S.ed25519_verify(S.ed25519_public(seed), msg, k.sign(msg))


def test_minisign_keys_read_and_write(tmp_path, key):
    # minisign's README key: its id is printed as minisign prints it
    readme = S.parse_public_key("RWQf6LRCGA9i53mlYecO4IzT51TGPpvWucNSCh1CBM0QTaLn73Y7GFO3")
    assert readme.id == "E7620F1842B4E81F"
    pub = key["public"].read_text(encoding="utf-8")
    assert pub.startswith(f"untrusted comment: minisign public key {key['id']}\nRW")
    # the line, the whole file, its path: the same key
    assert S.parse_public_key(key["b64"]) == S.parse_public_key(pub) == S.parse_public_key(str(key["public"]))
    for bad in ("", "RWQnope", "untrusted comment: x\nAAAA"):
        with pytest.raises(S.SignatureError) as e:
            S.parse_public_key(bad)
        assert e.value.problem.code == "sign_key_bad"
    # the secret: readable by this user only, never overwritten
    assert oct(key["secret"].stat().st_mode & 0o777) == "0o600"
    sk = S.parse_secret_key(key["secret"])
    assert sk.public == S.parse_public_key(pub)
    with pytest.raises(S.SignatureError) as e:
        S.keygen(key["secret"])
    assert e.value.problem.code == "sign_key_exists"
    # damaged: the checksum says it
    raw = bytearray(base64.b64decode(key["secret"].read_text().splitlines()[1]))
    raw[70] ^= 1
    with pytest.raises(S.SignatureError) as e:
        S.parse_secret_key("untrusted comment: x\n" + base64.b64encode(bytes(raw)).decode())
    assert e.value.problem.code == "sign_secret_bad"


def test_an_encrypted_key_needs_its_password(tmp_path, monkeypatch):
    sk = S.generate_key()
    try:
        text = S.secret_key_text(sk, "segreta")
    except S.SignatureError as exc:      # no scrypt in this Python: said, and -W keys still work
        assert exc.problem.code == "sign_key_encrypted"
        pytest.skip("no scrypt here")
    assert "encrypted" in text.splitlines()[0]
    monkeypatch.delenv(S.PASSWORD_ENV, raising=False)
    with pytest.raises(S.SignatureError) as e:
        S.parse_secret_key(text)
    assert e.value.problem.code == "sign_password_needed"
    with pytest.raises(S.SignatureError) as e:
        S.parse_secret_key(text, "sbagliata")
    assert e.value.problem.code == "sign_password_wrong"
    monkeypatch.setenv(S.PASSWORD_ENV, "segreta")
    assert S.parse_secret_key(text).seed == sk.seed


def test_a_signature_is_minisigns_and_says_what_changed(tmp_path):
    sk = S.generate_key()
    data = b"ESEMPIO " * 1000
    sig = S.sign_bytes(sk, data, "em-extension\tid:x\tversion:1.0.0\thashed")
    text = sig.text()
    lines = text.splitlines()
    assert len(lines) == 4 and lines[0].startswith("untrusted comment: ") and lines[2].startswith("trusted comment: ")
    assert base64.b64decode(lines[1])[:2] == b"ED"            # prehashed, minisign's default
    assert S.sign_bytes(sk, data, sig.trusted).text() == text  # deterministic
    p = S.parse_signature(text)
    assert S.verify_bytes(p, data, [sk.public]) == sk.public
    with pytest.raises(S.SignatureError) as e:
        S.verify_bytes(p, data + b"!", [sk.public])
    assert e.value.problem.code == "sign_mismatch"
    forged = text.replace("version:1.0.0", "version:9.9.9")
    with pytest.raises(S.SignatureError) as e:
        S.verify_bytes(S.parse_signature(forged), data, [sk.public])
    assert e.value.problem.code == "sign_comment_forged"
    with pytest.raises(S.SignatureError) as e:
        S.verify_bytes(p, data, [S.generate_key().public])
    assert e.value.problem.code == "sign_key_unknown" and sk.id in e.value.problem.text("it")
    # the legacy form (Ed: the whole message) verifies too
    legacy = S.ed25519_sign(sk.seed, data)
    gsig = S.ed25519_sign(sk.seed, legacy + b"legacy")
    old = S.Signature(b"Ed", sk.key_id, legacy, "legacy", gsig)
    assert S.verify_bytes(S.parse_signature(old.text()), data, [sk.public]) == sk.public
    with pytest.raises(S.SignatureError):
        S.parse_signature("not\na\nsignature")


# ── the repository signs ────────────────────────────────────────────────────

def test_server_generate_signs_every_archive_and_the_index(repo, key):
    z = entry_file(repo, "facemesh_fit")
    sig = S.parse_signature((repo / (z.name + ".minisig")).read_text(encoding="utf-8"))
    f = sig.fields()
    idx = json.loads((repo / "index.json").read_text(encoding="utf-8"))
    e = next(x for x in idx["data"] if x["id"] == "facemesh_fit")
    assert f["id"] == "facemesh_fit" and f["version"] == e["version"] and f["archive_hash"] == e["archive_hash"]
    assert "timestamp" not in sig.trusted            # deterministic: the same bytes every time
    assert (repo / "index.json.minisig").is_file() and (repo / S.PUB_FILE).read_text() == key["public"].read_text()
    # the index itself stays as an unsigned server-generate writes it (the CI's --check)
    assert "minisig" not in (repo / "index.json").read_text(encoding="utf-8")
    before = {p.name: p.read_bytes() for p in repo.glob("*.minisig")}
    assert X.server_generate(repo, check=True, sign_key=key["secret"])["ok"]
    X.server_generate(repo, sign_key=key["secret"])
    assert {p.name: p.read_bytes() for p in repo.glob("*.minisig")} == before
    v = X.verify_repository(repo, [key["public"]])
    assert v["ok"] and len(v["verified"]) == 2
    # another key verifies nothing
    v = X.verify_repository(repo, [S.generate_key().public])
    assert not v["ok"] and {p["code"] for p in v["problems"]} == {"sign_key_unknown"}


def test_signing_never_blesses_other_bytes(repo, key):
    z = entry_file(repo, "esempio-statuaria")
    z.write_bytes(z.read_bytes() + b"\0")          # changed after the index was written
    res = X.sign_repository(repo, key["secret"])
    assert not res["ok"] and [p["code"] for p in res["problems"]] == ["sign_hash_other"]
    v = X.verify_repository(repo, [key["b64"]])
    assert not v["ok"] and "sign_mismatch" in [p["code"] for p in v["problems"]]


# ── the client of a signed repository ───────────────────────────────────────

def test_a_signed_repository_is_read_and_installed_signed(repo, key):
    r = X.add_repository(str(repo), name="lab", keys=[str(key["public"])])
    assert r["signed"] and r["keys"] == [{"key_id": key["id"], "key": key["b64"]}]
    got = X.sync("lab")["repositories"][0]
    assert got["ok"] and got["signed_by"] == key["id"]
    assert X.get_repository("lab")["signed_by"] == key["id"]
    a = {x["id"]: x for x in X.available("lab")["available"]}
    assert a["facemesh_fit"]["signed"] and a["facemesh_fit"]["signed_by"] == key["id"]
    pv = X.preview_from("lab", "facemesh_fit")
    assert pv["repository"]["signed"]["key_id"] == key["id"] and pv["repository"]["signed_repository"]
    assert pv["signature"]["status"] == "signed" and pv["signature"]["repos"] == ["lab"]
    # a signature is not a review: the trust question stays
    assert pv["code"]["trust_needed"] and not pv["code"]["verified"]
    done = X.install_from("lab", "facemesh_fit", trust=True)
    row = X.get("facemesh_fit")
    assert row["signed"] == {"key_id": key["id"], "repos": ["lab"]}
    assert "sign_signed" in [w["code"] for w in done["installed"]["warnings"]]
    assert row["code"]["trusted_by"] == "person"


def test_a_mirror_that_changes_index_and_archive_together_is_refused(repo, key):
    X.add_repository(str(repo), name="lab", keys=key["b64"])
    assert X.sync("lab")["repositories"][0]["ok"]
    good = (repo / "index.json").read_bytes()
    # the mirror: another archive and an index written for it, without the key
    z = entry_file(repo, "esempio-statuaria")
    z.write_bytes(z.read_bytes() + b"\0")
    X.server_generate(repo)
    got = X.sync("lab")["repositories"][0]
    assert not got["ok"] and got["problems"][0]["code"] == "sign_mismatch"
    assert RM.cached_index("lab") == json.loads(good)          # the previous copy stays
    # no signature at all
    (repo / "index.json.minisig").unlink()
    got = X.sync("lab")["repositories"][0]
    assert not got["ok"] and got["problems"][0]["code"] == "sign_index_missing"
    assert "resta la copia di prima" in got["problems"][0]["it"]


def test_an_archive_must_carry_the_signature_of_its_entry(repo, key):
    X.add_repository(str(repo), name="lab", keys=key["b64"])
    X.sync("lab")
    zf, zs = entry_file(repo, "facemesh_fit"), entry_file(repo, "esempio-statuaria")
    sf, ss = (Path(str(z) + ".minisig") for z in (zf, zs))
    # the signature of another archive (a valid one, by the same key)
    keep = sf.read_bytes()
    sf.write_bytes(ss.read_bytes())
    with pytest.raises(X.RepoError) as e:
        X.download("lab", "facemesh_fit")
    assert e.value.report.codes() == ["sign_mismatch"]
    sf.unlink()
    with pytest.raises(X.RepoError) as e:
        X.preview_from("lab", "facemesh_fit")
    assert e.value.report.codes() == ["sign_archive_unsigned"]
    sf.write_bytes(keep)
    assert X.download("lab", "facemesh_fit")["signed"]["id"] == "facemesh_fit"
    # the entry's archive_hash is what the comment must name: a signature over the same bytes
    # with another version in its comment is refused (sopra archive_hash)
    sk = S.parse_secret_key(key["secret"])
    S.sign_file(sk, zf, S.archive_comment("facemesh_fit", "9.9.9", S._sha256(zf), zf.name))
    (X.extensions_dir() / "archives" / "lab").exists() and shutil.rmtree(X.extensions_dir() / "archives" / "lab")
    with pytest.raises(X.RepoError) as e:
        X.download("lab", "facemesh_fit")
    assert e.value.report.codes() == ["sign_entry_other"]


def test_an_unsigned_repository_works_as_before(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    built(SEPARATE, d)
    assert X.server_generate(d)["ok"]
    r = X.add_repository(str(d), name="plain")
    assert not r["signed"] and r["keys"] == []
    assert X.sync("plain")["repositories"][0]["ok"]
    got = X.download("plain", "esempio-statuaria")
    assert got["signed"] is None
    assert X.preview(got["path"])["signature"] is None


def test_changing_the_keys_keeps_the_copy_only_if_it_verifies(repo, key):
    X.add_repository(str(repo), name="lab")
    X.sync("lab")
    assert RM.cached_index("lab") is not None and X.get_repository("lab")["signed_by"] is None
    # no .minisig in the cache yet (read unsigned): with keys, the copy goes
    X.update_repository("lab", keys=[key["b64"]])
    assert RM.cached_index("lab") is None
    assert X.sync("lab")["repositories"][0]["signed_by"] == key["id"]
    # another key: the copy does not verify with it, it goes
    other = S.generate_key().public.b64()
    X.update_repository("lab", keys=[other])
    assert RM.cached_index("lab") is None
    X.update_repository("lab", keys=[key["b64"], other])
    X.sync("lab")
    X.update_repository("lab", keys=[key["b64"]])           # still verifies: stays
    assert RM.cached_index("lab") is not None
    out = X.update_repository("lab", keys=[])
    assert not out["signed"] and RM.cached_index("lab") is not None and out["signed_by"] is None
    with pytest.raises(X.RepoError) as e:
        X.add_repository("/tmp/elsewhere", name="x", keys=["RWQnope"])
    assert e.value.report.codes() == ["sign_key_bad"]


# ── from disk ───────────────────────────────────────────────────────────────

def test_an_archive_from_disk_with_its_signature(repo, key, tmp_path):
    z = entry_file(repo, "esempio-statuaria")
    # nobody here names the key: said, not refused
    pv = X.preview(z)
    assert pv["signature"]["status"] == "unknown_key" and pv["ok"]
    assert "sign_key_unknown_here" in [w["code"] for w in pv["warnings"]]
    X.add_repository(str(repo), name="lab", keys=key["b64"])
    pv = X.preview(z)
    assert pv["signature"]["status"] == "signed" and pv["signature"]["repos"] == ["lab"]
    row = X.install(z)
    assert row["signed"]["key_id"] == key["id"]
    # a known key, other bytes: refused, nothing written
    copy = tmp_path / "copy"
    copy.mkdir()
    bad = copy / z.name
    bad.write_bytes(z.read_bytes() + b"\0")
    shutil.copy(str(z) + ".minisig", str(bad) + ".minisig")
    pv = X.preview(bad)
    assert not pv["ok"] and [e["code"] for e in pv["errors"]] == ["sign_mismatch"]
    with pytest.raises(X.ExtensionError) as e:
        X.install(bad)
    assert e.value.report.codes() == ["sign_mismatch"]
    # without its .minisig, an archive is simply not signed
    os_sig = Path(str(bad) + ".minisig")
    os_sig.unlink()
    assert X.preview(bad)["signature"] is None


def test_sign_archive_for_a_curator_who_sends_a_zip(tmp_path, key):
    z = built(PLUGIN, tmp_path)
    res = X.sign_archive(z, key["secret"])
    assert res["id"] == "facemesh_fit" and Path(res["signature"]).is_file()
    X.add_repository(str(tmp_path / "somewhere"), name="curatore", keys=key["b64"])
    assert X.preview(z)["signature"]["status"] == "signed"


# ── the command line, the messages ──────────────────────────────────────────

def test_the_command_line(tmp_path, capsys, monkeypatch):
    d = tmp_path / "lab"
    d.mkdir()
    built(SEPARATE, d)
    sk = tmp_path / "k" / "lab.key"
    assert cli.main(["sign", "keygen", str(sk)]) == 0
    pub = json.loads(capsys.readouterr().out)["public"]
    assert cli.main(["sign", "keygen", str(sk), "--lang", "it"]) == 1
    assert "non si sovrascrive" in capsys.readouterr().err
    monkeypatch.delenv(S.PASSWORD_ENV, raising=False)
    assert cli.main(["sign", "keygen", str(tmp_path / "k2"), "--encrypt"]) == 1
    assert "S3DGRAPHY_SIGN_PASSWORD" in capsys.readouterr().err
    assert cli.main(["server-generate", "--repo-dir", str(d), "--sign-key", str(sk), "--lang", "it"]) == 0
    assert "firmato con la chiave" in capsys.readouterr().out
    assert cli.main(["sign", "verify", "--repo-dir", str(d), "--key", pub]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert cli.main(["repo", "add", str(d), "--name", "lab", "--key", pub]) == 0
    assert json.loads(capsys.readouterr().out)["signed"]
    assert cli.main(["repo", "sync", "lab"]) == 0
    capsys.readouterr()
    z = next(d.glob("*.zip"))
    assert cli.main(["sign", "check", str(z)]) == 0
    assert json.loads(capsys.readouterr().out)["signature"]["status"] == "signed"
    assert cli.main(["repo", "keys", "lab", "--clear"]) == 0
    assert not json.loads(capsys.readouterr().out)["signed"]


def test_every_message_in_two_languages():
    codes = [c for c in MESSAGES if c.startswith("sign_")]
    assert len(codes) == 21
    for c in codes:
        en, it = MESSAGES[c]
        assert en and it and en != it
        assert set(re.findall(r"{(\w+)", en)) == set(re.findall(r"{(\w+)", it)), c
