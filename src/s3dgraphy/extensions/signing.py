"""The signature of a repository: minisign over ``archive_hash`` (X8).

MICRO-PL28-FIRMA, row X8 of the extensions plan (E.D., 18–19 Nov 2026:
«X8 firma con minisign/sigstore sopra ``archive_hash``»). Until X8 the
guarantee was Blender's: the ``archive_hash`` of an index served by a
repository the person added (SPEC-plugin §16.3). It holds as long as the
index comes from where the person thinks; a mirror, a NAS copy, a proxy or a
repository's hosting that someone else controls can change the index and the
archives together. A signature moves the trust from *where the bytes came
from* to *who holds the key*.

**minisign, not sigstore** (the evaluation the row asked for, in the
report): a minisign signature is an Ed25519 signature in a four-line text
file; it is verified offline, by a ``file://`` repository on a NAS (D-13) as
by an https one, with a public key the person pastes once — the way a
curator already gives the URL. Sigstore needs an OIDC identity, Fulcio and
the Rekor log on the network at signing and (for the log) at verifying, and
a dependency the library does not have. Everything here is the standard
library: Ed25519 (RFC 8032) and BLAKE2b in pure Python, so EMStudio's
bridge, Blender's Python and the node verify alike.

**The files are minisign's own** (https://jedisct1.github.io/minisign/):
``minisign -Vm foo.zip -p repo.pub`` verifies what :func:`sign_file` writes,
and a key made by ``minisign -G`` (encrypted when a scrypt is available,
``-W`` always) signs here.

**What is signed** — the repository's two kinds of bytes, each with a
sidecar ``.minisig`` (never inside ``index.json``: the committed index of a
repository whose CI checks it with ``--check`` stays the same bytes, and the
key is needed only where the archives are published):

* ``<archive>.zip.minisig`` — the archive's bytes (prehashed, minisign's
  ``ED``), and in the **trusted comment** (signed too) ``id``, ``version``
  and the ``archive_hash`` the index lists: a signature binds the bytes to
  the entry, «sopra archive_hash»;
* ``index.json.minisig`` — the index's bytes: the ``blocklist`` and the
  ``reviewed`` (X4) are in the index only, and they are what a mirror would
  forge first.

No timestamp in the trusted comment: Ed25519 is deterministic, so the same
key over the same archives writes the same signatures.

What a signature does NOT do: it says who published the archive, not that
anyone read the code. The trust question stays (a reviewed code is X4's).
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from ..profiles.problems import Problem, Report

SIG_SUFFIX = ".minisig"
PUB_FILE = "minisign.pub"
PASSWORD_ENV = "S3DGRAPHY_SIGN_PASSWORD"
#: what the trusted comment of an archive's signature starts with
COMMENT_TAG = "em-extension"

Bytes = Union[bytes, bytearray]


class SignatureError(ValueError):
    """A key or a signature could not be read, made or verified; ``report`` says why, EN + IT."""

    def __init__(self, code: str, **params: Any):
        self.report = Report()
        self.report.error(code, **params)
        self.problem = self.report.problems[0]
        super().__init__(str(self.problem))


# ── Ed25519 (RFC 8032), pure Python ─────────────────────────────────────────
# Extended twisted Edwards coordinates; enough for a few signatures a second.

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _inv(x: int) -> int:
    return pow(x, _P - 2, _P)


def _add(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa = (y1 - x1) * (y2 - x2) % _P
    bb = (y1 + x1) * (y2 + x2) % _P
    cc = 2 * t1 * t2 * _D % _P
    dd = 2 * z1 * z2 % _P
    e, f, g, h = bb - aa, dd - cc, dd + cc, bb + aa
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s: int, p: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _equal(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    return (a[0] * b[2] - b[0] * a[2]) % _P == 0 and (a[1] * b[2] - b[1] * a[2]) % _P == 0


def _recover_x(y: int, sign: int) -> Optional[int]:
    if y >= _P:
        return None
    x2 = (y * y - 1) * _inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _I % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * _inv(5) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(p: Tuple[int, int, int, int]) -> bytes:
    zi = _inv(p[2])
    x, y = p[0] * zi % _P, p[1] * zi % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes) -> Optional[Tuple[int, int, int, int]]:
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h(*parts: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b"".join(parts)).digest(), "little")


def _expand(seed: bytes) -> Tuple[int, bytes]:
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public(seed: bytes) -> bytes:
    """The 32-byte public key of a 32-byte seed."""
    a, _ = _expand(seed)
    return _compress(_mul(a, _G))


def ed25519_sign(seed: bytes, msg: bytes) -> bytes:
    """The 64-byte signature of ``msg`` (deterministic, RFC 8032 §5.1.6)."""
    a, prefix = _expand(seed)
    pub = _compress(_mul(a, _G))
    r = _h(prefix, msg) % _L
    rs = _compress(_mul(r, _G))
    k = _h(rs, pub, msg) % _L
    s = (r + k * a) % _L
    return rs + int.to_bytes(s, 32, "little")


def ed25519_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    """Whether ``sig`` is the signature of ``msg`` under ``pub`` (RFC 8032 §5.1.7)."""
    if len(pub) != 32 or len(sig) != 64:
        return False
    a = _decompress(pub)
    r = _decompress(sig[:32])
    if a is None or r is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = _h(sig[:32], pub, msg) % _L
    return _equal(_mul(s, _G), _add(r, _mul(k, a)))


# ── minisign's keys ─────────────────────────────────────────────────────────

_ALG_KEY = b"Ed"          # the key's algorithm; a signature: b"Ed" (legacy) or b"ED" (prehashed)
_KDF_SCRYPT = b"Sc"
_KDF_NONE = b"\x00\x00"
_CHK = b"B2"
#: minisign's own scrypt limits (N = 2^20, r = 8, p = 1): a key made here opens with ``minisign``
_OPSLIMIT = 33554432
_MEMLIMIT = 1073741824


def key_id_hex(key_id: bytes) -> str:
    """The key id as minisign prints it (the 8 bytes as a little-endian number, upper hex)."""
    return key_id[::-1].hex().upper()


class PublicKey:
    """A minisign public key: ``key_id`` (8 bytes) and the Ed25519 key."""

    def __init__(self, key_id: bytes, key: bytes, comment: str = ""):
        self.key_id, self.key, self.comment = bytes(key_id), bytes(key), comment

    @property
    def id(self) -> str:
        return key_id_hex(self.key_id)

    def b64(self) -> str:
        return base64.b64encode(_ALG_KEY + self.key_id + self.key).decode("ascii")

    def text(self) -> str:
        """The ``minisign.pub`` file."""
        return f"untrusted comment: minisign public key {self.id}\n{self.b64()}\n"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PublicKey) and other.key_id == self.key_id and other.key == self.key

    def __hash__(self) -> int:
        return hash((self.key_id, self.key))

    def __repr__(self) -> str:
        return f"PublicKey({self.id})"


class SecretKey:
    """A minisign secret key: ``key_id``, the 32-byte seed, its public key."""

    def __init__(self, key_id: bytes, seed: bytes):
        self.key_id, self.seed = bytes(key_id), bytes(seed)
        self.public = PublicKey(self.key_id, ed25519_public(self.seed))

    @property
    def id(self) -> str:
        return key_id_hex(self.key_id)

    def __repr__(self) -> str:
        return f"SecretKey({self.id})"


def parse_public_key(text: Any) -> PublicKey:
    """A public key from what a person pastes: the base64 line (``RW…``), the
    whole ``minisign.pub`` file, or a path to it."""
    s = str(text or "").strip()
    if s and "\n" not in s and not s.startswith("RW") and Path(s).expanduser().is_file():
        s = Path(s).expanduser().read_text(encoding="utf-8").strip()
    lines = [ln.strip() for ln in s.splitlines() if ln.strip() and not ln.strip().startswith("untrusted comment:")]
    if len(lines) != 1:
        raise SignatureError("sign_key_bad", what=_short(s))
    try:
        raw = base64.b64decode(lines[0], validate=True)
    except (ValueError, TypeError):
        raise SignatureError("sign_key_bad", what=_short(lines[0])) from None
    if len(raw) != 42 or raw[:2] != _ALG_KEY:
        raise SignatureError("sign_key_bad", what=_short(lines[0]))
    return PublicKey(raw[2:10], raw[10:42])


def _short(s: str) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= 60 else s[:57] + "…"


def _scrypt_params(opslimit: int, memlimit: int) -> Tuple[int, int, int]:
    """libsodium's ``pickparams`` (crypto_pwhash_scryptsalsa208sha256): N, r, p."""
    opslimit = max(opslimit, 32768)
    r = 8
    if opslimit < memlimit // 32:
        p = 1
        max_n = opslimit // (r * 4)
        n_log2 = 1
        while n_log2 < 63 and (1 << n_log2) <= max_n // 2:
            n_log2 += 1
    else:
        max_n = memlimit // (r * 128)
        n_log2 = 1
        while n_log2 < 63 and (1 << n_log2) <= max_n // 2:
            n_log2 += 1
        max_rp = min((opslimit // 4) // (1 << n_log2), 0x3FFFFFFF)
        p = max_rp // r
    return 1 << n_log2, r, max(p, 1)


def _scrypt(password: bytes, salt: bytes, opslimit: int, memlimit: int, length: int) -> bytes:
    n, r, p = _scrypt_params(opslimit, memlimit)
    fn = getattr(hashlib, "scrypt", None)
    if fn is not None:
        return fn(password, salt=salt, n=n, r=r, p=p, maxmem=128 * r * n * p + 256 * r * p + 128 * r * 2 ** 10 + 2 ** 20,
                  dklen=length)
    try:   # an OpenSSL without scrypt (macOS' LibreSSL): the optional ``cryptography``
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError:
        raise SignatureError("sign_key_encrypted") from None
    return Scrypt(salt=salt, length=length, n=n, r=r, p=p).derive(password)


def _checksum(key_id: bytes, sk64: bytes) -> bytes:
    return hashlib.blake2b(_ALG_KEY + key_id + sk64, digest_size=32).digest()


def generate_key() -> SecretKey:
    """A new key (the CI's, a curator's)."""
    return SecretKey(secrets.token_bytes(8), secrets.token_bytes(32))


def secret_key_text(key: SecretKey, password: Optional[str] = None) -> str:
    """The secret key file, minisign's format: encrypted with ``password``
    (scrypt, minisign's parameters), or not (``minisign -W``)."""
    sk64 = key.seed + key.public.key
    keynum = key.key_id + sk64 + _checksum(key.key_id, sk64)
    if password:
        salt = secrets.token_bytes(32)
        stream = _scrypt(password.encode("utf-8"), salt, _OPSLIMIT, _MEMLIMIT, len(keynum))
        keynum = bytes(a ^ b for a, b in zip(keynum, stream))
        head = _ALG_KEY + _KDF_SCRYPT + _CHK + salt + _OPSLIMIT.to_bytes(8, "little") + _MEMLIMIT.to_bytes(8, "little")
        comment = "minisign encrypted secret key"
    else:
        head = _ALG_KEY + _KDF_NONE + _CHK + bytes(32) + bytes(16)
        comment = "minisign secret key, not encrypted"
    return f"untrusted comment: {comment}\n{base64.b64encode(head + keynum).decode('ascii')}\n"


def parse_secret_key(text: Any, password: Optional[str] = None) -> SecretKey:
    """A secret key from its file's text or path (``password``, or
    ``S3DGRAPHY_SIGN_PASSWORD``, for an encrypted one)."""
    s = str(text or "")
    if "\n" not in s.strip() and Path(s.strip()).expanduser().is_file():
        s = Path(s.strip()).expanduser().read_text(encoding="utf-8")
    lines = [ln.strip() for ln in s.splitlines() if ln.strip() and not ln.strip().startswith("untrusted comment:")]
    try:
        raw = base64.b64decode(lines[0], validate=True) if len(lines) == 1 else b""
    except (ValueError, TypeError):
        raw = b""
    if len(raw) != 158 or raw[:2] != _ALG_KEY or raw[4:6] != _CHK:
        raise SignatureError("sign_secret_bad")
    kdf, salt = raw[2:4], raw[6:38]
    ops, mem = int.from_bytes(raw[38:46], "little"), int.from_bytes(raw[46:54], "little")
    keynum = raw[54:]
    if kdf == _KDF_SCRYPT:
        pw = password if password is not None else os.environ.get(PASSWORD_ENV)
        if not pw:
            raise SignatureError("sign_password_needed")
        stream = _scrypt(pw.encode("utf-8"), salt, ops, mem, len(keynum))
        keynum = bytes(a ^ b for a, b in zip(keynum, stream))
    elif kdf != _KDF_NONE:
        raise SignatureError("sign_secret_bad")
    key_id, sk64, chk = keynum[:8], keynum[8:72], keynum[72:104]
    if _checksum(key_id, sk64) != chk:
        raise SignatureError("sign_password_wrong" if kdf == _KDF_SCRYPT else "sign_secret_bad")
    key = SecretKey(key_id, sk64[:32])
    if key.public.key != sk64[32:]:
        raise SignatureError("sign_secret_bad")
    return key


def keygen(secret_path: Any, public_path: Any = None, *, password: Optional[str] = None,
           force: bool = False) -> Dict[str, Any]:
    """Write a new key pair: the secret readable by this user only, the
    public next to it (``minisign.pub`` by default). Never over an existing
    secret key unless ``force``."""
    sp = Path(secret_path).expanduser()
    pp = Path(public_path).expanduser() if public_path else sp.with_name(PUB_FILE)
    if sp.exists() and not force:
        raise SignatureError("sign_key_exists", path=str(sp))
    key = generate_key()
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_name(sp.name + ".tmp")
    tmp.write_text(secret_key_text(key, password), encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(sp)
    pp.write_text(key.public.text(), encoding="utf-8")
    return {"key_id": key.id, "public_key": key.public.b64(), "secret": str(sp), "public": str(pp),
            "encrypted": bool(password)}


# ── minisign's signatures ───────────────────────────────────────────────────

class Signature:
    """A ``.minisig``: algorithm, key id, the signature, the trusted comment and its signature."""

    def __init__(self, alg: bytes, key_id: bytes, sig: bytes, trusted: str, global_sig: bytes,
                 untrusted: str = ""):
        self.alg, self.key_id, self.sig = alg, key_id, sig
        self.trusted, self.global_sig, self.untrusted = trusted, global_sig, untrusted

    @property
    def id(self) -> str:
        return key_id_hex(self.key_id)

    def text(self) -> str:
        return (f"untrusted comment: {self.untrusted}\n"
                f"{base64.b64encode(self.alg + self.key_id + self.sig).decode('ascii')}\n"
                f"trusted comment: {self.trusted}\n"
                f"{base64.b64encode(self.global_sig).decode('ascii')}\n")

    def fields(self) -> Dict[str, str]:
        """The trusted comment's ``key:value`` fields (tab-separated, as minisign's own)."""
        out = {}
        for part in self.trusted.split("\t"):
            k, sep, v = part.partition(":")
            if sep:
                out[k.strip()] = v.strip()
        return out


def parse_signature(text: Any) -> Signature:
    s = text.decode("utf-8", "replace") if isinstance(text, (bytes, bytearray)) else str(text or "")
    lines = s.splitlines()
    if len(lines) < 4 or not lines[0].startswith("untrusted comment: ") \
            or not lines[2].startswith("trusted comment: "):
        raise SignatureError("sign_signature_bad")
    try:
        raw = base64.b64decode(lines[1].strip(), validate=True)
        gsig = base64.b64decode(lines[3].strip(), validate=True)
    except (ValueError, TypeError):
        raise SignatureError("sign_signature_bad") from None
    if len(raw) != 74 or raw[:2] not in (b"Ed", b"ED") or len(gsig) != 64:
        raise SignatureError("sign_signature_bad")
    return Signature(raw[:2], raw[2:10], raw[10:74], lines[2][len("trusted comment: "):], gsig,
                     lines[0][len("untrusted comment: "):])


def _prehash(data: Union[Bytes, Path]) -> bytes:
    h = hashlib.blake2b(digest_size=64)
    if isinstance(data, Path):
        with data.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    else:
        h.update(data)
    return h.digest()


def sign_bytes(key: SecretKey, data: Union[Bytes, Path], trusted_comment: str,
               untrusted_comment: Optional[str] = None) -> Signature:
    """minisign's prehashed signature (``ED``) of ``data`` with a trusted comment."""
    if "\n" in trusted_comment or "\r" in trusted_comment:
        raise SignatureError("sign_comment_bad")
    sig = ed25519_sign(key.seed, _prehash(data))
    gsig = ed25519_sign(key.seed, sig + trusted_comment.encode("utf-8"))
    return Signature(b"ED", key.key_id, sig, trusted_comment, gsig,
                     untrusted_comment or f"signature from minisign secret key {key.id}")


def verify_bytes(sig: Signature, data: Union[Bytes, Path], keys: Iterable[PublicKey]) -> PublicKey:
    """The key that made ``sig`` over ``data``, or :class:`SignatureError`:
    ``sign_key_unknown`` (none of ``keys`` has its id), ``sign_mismatch``
    (the bytes are not those signed), ``sign_comment_forged`` (the trusted
    comment was changed)."""
    key = next((k for k in keys if k.key_id == sig.key_id), None)
    if key is None:
        raise SignatureError("sign_key_unknown", key_id=sig.id)
    if sig.alg == b"ED":
        msg = _prehash(data)
    else:   # the legacy, non-prehashed form: the whole message
        msg = data.read_bytes() if isinstance(data, Path) else bytes(data)
    if not ed25519_verify(key.key, msg, sig.sig):
        raise SignatureError("sign_mismatch", key_id=sig.id)
    if not ed25519_verify(key.key, sig.sig + sig.trusted.encode("utf-8"), sig.global_sig):
        raise SignatureError("sign_comment_forged", key_id=sig.id)
    return key


# ── what a repository signs ─────────────────────────────────────────────────

def _sha256(data: Union[Bytes, Path]) -> str:
    h = hashlib.sha256()
    if isinstance(data, Path):
        with data.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    else:
        h.update(data)
    return "sha256:" + h.hexdigest()


def archive_comment(eid: str, version: str, archive_hash: str, file_name: str) -> str:
    """The trusted comment of an archive's signature: what the index says of it."""
    return (f"{COMMENT_TAG}\tid:{eid}\tversion:{version}\tarchive_hash:{archive_hash}"
            f"\tfile:{file_name}\thashed")


def index_comment(index_hash: str) -> str:
    return f"{COMMENT_TAG}-index\tsha256:{index_hash.split(':', 1)[-1]}\tfile:index.json\thashed"


def sign_file(key: SecretKey, path: Any, trusted_comment: str) -> Path:
    """``<path>.minisig`` next to the file; returns its path."""
    p = Path(path)
    sig = sign_bytes(key, p, trusted_comment)
    out = p.with_name(p.name + SIG_SUFFIX)
    out.write_text(sig.text(), encoding="utf-8")
    return out


def sign_archive(path: Any, key: Any, *, password: Optional[str] = None) -> Dict[str, Any]:
    """One archive signed on its own (a curator who sends a zip by hand): the
    trusted comment from its envelope (``id``, ``version``) and its bytes."""
    from ..profiles.package import open_package
    p = Path(path).expanduser()
    sk = key if isinstance(key, SecretKey) else parse_secret_key(key, password)
    pkg = open_package(p)
    version = str((pkg.envelope or {}).get("version") or pkg.data_version or "")
    got = _sha256(p)
    out = sign_file(sk, p, archive_comment(str(pkg.id), version, got, p.name))
    return {"ok": True, "key_id": sk.id, "id": pkg.id, "version": version, "archive_hash": got,
            "signature": str(out)}


def check_archive(sig_text: Any, data: Union[Bytes, Path], keys: Iterable[PublicKey],
                  entry: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """An archive's signature checked: the key, the bytes, and — the point of
    signing «over archive_hash» — the trusted comment's ``archive_hash`` is
    the bytes' own and, given an index entry, its ``id``, ``version`` and
    ``archive_hash`` are the entry's. Returns ``{key_id, id, version,
    archive_hash}``; raises :class:`SignatureError`."""
    sig = parse_signature(sig_text)
    verify_bytes(sig, data, keys)
    f = sig.fields()
    if not sig.trusted.startswith(COMMENT_TAG + "\t") or not f.get("archive_hash"):
        raise SignatureError("sign_not_archive", key_id=sig.id)
    got = _sha256(data)
    if f["archive_hash"] != got:
        raise SignatureError("sign_hash_other", key_id=sig.id, want=f["archive_hash"], got=got)
    if entry is not None:
        for k in ("id", "version", "archive_hash"):
            if str(entry.get(k)) != f.get(k):
                raise SignatureError("sign_entry_other", key_id=sig.id, key=k, signed=f.get(k) or "",
                                     index=str(entry.get(k)))
    return {"key_id": sig.id, "id": f.get("id"), "version": f.get("version"), "archive_hash": f["archive_hash"]}


def check_index(sig_text: Any, blob: Bytes, keys: Iterable[PublicKey]) -> Dict[str, Any]:
    """An index's signature checked (its bytes, and that it was signed as an index)."""
    sig = parse_signature(sig_text)
    verify_bytes(sig, blob, keys)
    if not sig.trusted.startswith(COMMENT_TAG + "-index\t"):
        raise SignatureError("sign_not_index", key_id=sig.id)
    return {"key_id": sig.id, "sha256": sig.fields().get("sha256")}


def sign_repository(repo_dir: Any, key: Any, *, password: Optional[str] = None,
                    index: Any = None) -> Dict[str, Any]:
    """Sign a repository folder after :func:`server_generate`: every archive
    the index lists (found by its file name), then the index. Archives the
    index does not list are not signed; an archive whose bytes are not the
    index's ``archive_hash`` is refused (signing must never bless other
    bytes). Writes ``minisign.pub`` beside, for whoever adds the repository."""
    import json
    from .repository import INDEX_FILE
    root = Path(repo_dir).expanduser()
    sk = key if isinstance(key, SecretKey) else parse_secret_key(key, password)
    ip = Path(index).expanduser() if index else root / INDEX_FILE
    rep = Report()
    try:
        blob = ip.read_bytes()
        doc = json.loads(blob.decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SignatureError("sign_no_index", path=str(ip), why=str(exc)) from exc
    signed: List[Dict[str, Any]] = []
    for e in doc.get("data") or []:
        name = str(e.get("archive_url") or "").rsplit("/", 1)[-1]
        f = root / name
        if not name or not f.is_file():
            rep.error("sign_archive_missing", id=str(e.get("id")), file=name)
            continue
        got = _sha256(f)
        if got != e.get("archive_hash"):
            rep.error("sign_hash_other", key_id=sk.id, want=str(e.get("archive_hash")), got=got)
            continue
        out = sign_file(sk, f, archive_comment(str(e["id"]), str(e["version"]), got, name))
        signed.append({"file": name, "signature": out.name})
    if rep.errors:
        return {"ok": False, "key_id": sk.id, "signed": signed, "index": None,
                "problems": [p.as_dict() for p in rep.problems]}
    out = sign_file(sk, ip, index_comment(_sha256(blob)))
    (ip.parent / PUB_FILE).write_text(sk.public.text(), encoding="utf-8")
    return {"ok": True, "key_id": sk.id, "public_key": sk.public.b64(), "signed": signed, "index": out.name,
            "problems": [p.as_dict() for p in rep.problems]}


def verify_repository(repo_dir: Any, keys: Sequence[Any], *, index: Any = None) -> Dict[str, Any]:
    """What a client would check, on the folder: the index's signature and
    every listed archive's. ``keys``: public keys (text, path or :class:`PublicKey`)."""
    import json
    from .repository import INDEX_FILE
    root = Path(repo_dir).expanduser()
    pks = [k if isinstance(k, PublicKey) else parse_public_key(k) for k in keys]
    ip = Path(index).expanduser() if index else root / INDEX_FILE
    rep = Report()
    blob = ip.read_bytes()
    try:
        check_index(ip.with_name(ip.name + SIG_SUFFIX).read_text(encoding="utf-8"), blob, pks)
    except OSError:
        rep.error("sign_index_missing", name=str(root))
    except SignatureError as exc:
        rep.problems.append(exc.problem)
    ok_files = []
    for e in json.loads(blob.decode("utf-8")).get("data") or []:
        name = str(e.get("archive_url") or "").rsplit("/", 1)[-1]
        try:
            st = (root / (name + SIG_SUFFIX)).read_text(encoding="utf-8")
        except OSError:
            rep.error("sign_archive_unsigned", id=str(e.get("id")), version=str(e.get("version")))
            continue
        try:
            check_archive(st, root / name, pks, e)
            ok_files.append(name)
        except (SignatureError, OSError) as exc:
            rep.problems.append(exc.problem if isinstance(exc, SignatureError)
                                else Problem("sign_archive_missing", "error", "", {"id": e.get("id"), "file": name}))
    return {"ok": rep.ok, "verified": ok_files, "problems": [p.as_dict() for p in rep.problems]}


def describe_key(k: Any) -> Dict[str, str]:
    pk = k if isinstance(k, PublicKey) else parse_public_key(k)
    return {"key_id": pk.id, "key": pk.b64()}


__all__ = ["SIG_SUFFIX", "PUB_FILE", "PASSWORD_ENV", "SignatureError", "PublicKey", "SecretKey", "Signature",
           "parse_public_key", "parse_secret_key", "generate_key", "secret_key_text", "keygen", "parse_signature",
           "sign_bytes", "verify_bytes", "sign_file", "sign_archive", "archive_comment", "index_comment", "check_archive",
           "check_index", "sign_repository", "verify_repository", "describe_key", "key_id_hex",
           "ed25519_public", "ed25519_sign", "ed25519_verify"]
