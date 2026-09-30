"""The 3D Tiles Archive (``.3tz``) — recognised and read, never written here.

Specification: *3D Tiles Archive Format* v1.3
(github.com/erikdahlstrom/3tz-specification), media type
``application/vnd.maxar.archive.3tz+zip``. A 3tz is a zip with:

* ``tileset.json`` at the root;
* as the LAST entry of the central directory, the uncompressed index
  ``@3dtilesIndex1@``: 24-byte records, the MD5 of the normalised path
  (backslashes → slashes, no leading slash) followed by the little-endian uint64
  offset of that file's Local File Header, sorted by the MD5 read as two
  little-endian uint64 (first bytes 0-7, then 8-15);
* members stored (0), deflated (8) or Zstandard (93).

Why it is here: a tileset is a resource from its ROOT (``tileset.json``,
``packaging: directory``) or from its ZIPPED form (``packaging: archive``, one
file), decided by E.D. on 30 Sep 2026; a 3tz is the zipped form a viewer can
seek into. s3Dgraphy RECOGNISES it (``ResourceNode.effective_packaging`` reads a
``.3tz`` as ``archive``) and READS it (:func:`read_3tz_index`,
:func:`read_3tz_entry`, :func:`index_is_sorted`) without extracting.

WHO WRITES IT, and why not s3Dgraphy (E.D., 30 Sep 2026): packing a tileset is
DATA PREPARATION, not the graph's business. The writers are 3DSC
(``3D-survey-collection/cesium_exporter/archive_3tz.py``) and EMStudio. There is
ONE profile, 3DSC's, written down in :data:`CANONICAL_3TZ_PROFILE` (its
source text: ``dtcstamp/profiles/3tz.md``), and
:func:`is_canonical_3tz` says whether an archive follows it — the condition for
its sha256 to identify its content rather than the moment it was packed. The
canonical form and the digest of the CONTENT (independent of the packing) are
dtcstamp's to define (next MICRO); the writer that lived here until 20 Oct 2026
(``write_3tz``) is gone.

Pure Python: ``struct``, ``hashlib``, ``zlib``. Zstandard members need the
``zstandard`` package and say so when it is missing.
"""

from __future__ import annotations

import hashlib
import struct
import unicodedata
import zipfile
import zlib
from bisect import bisect_left
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

INDEX_NAME = "@3dtilesIndex1@"
MEDIA_TYPE_3TZ = "application/vnd.maxar.archive.3tz+zip"
_LFH_SIG = b"PK\x03\x04"
_LFH = struct.Struct("<4sHHHHHIIIHH")  # local file header, 30 bytes

PathLike = Union[str, Path]


def normalize_path(name: str) -> str:
    """The spec's normalisation: backslashes → slashes, leading slashes dropped."""
    return str(name).replace("\\", "/").lstrip("/")


def md5_key(digest: bytes) -> Tuple[int, int]:
    """The sort key of the spec: the MD5 as two little-endian uint64."""
    return struct.unpack("<QQ", digest)


def _index_bytes(zf: zipfile.ZipFile, fh) -> bytes:
    infos = zf.infolist()
    if not infos or infos[-1].filename != INDEX_NAME:
        raise ValueError(f"not a 3tz: the last entry is not {INDEX_NAME!r}")
    info = infos[-1]
    if info.compress_type != zipfile.ZIP_STORED:
        raise ValueError(f"not a 3tz: {INDEX_NAME} is compressed")
    return zf.read(info)


def read_3tz_index(path: PathLike) -> List[Tuple[bytes, int]]:
    """The index as ``[(md5, offset)]``, in the order it is written.

    Raises ValueError when the file is not a 3tz (index missing, not last,
    compressed, or not a multiple of 24 bytes)."""
    with open(path, "rb") as fh, zipfile.ZipFile(fh) as zf:
        raw = _index_bytes(zf, fh)
    if len(raw) % 24:
        raise ValueError(f"not a 3tz: index of {len(raw)} bytes is not 24-byte records")
    return [(raw[i:i + 16], struct.unpack_from("<Q", raw, i + 16)[0])
            for i in range(0, len(raw), 24)]


def _read_member_at(fh, offset: int) -> Tuple[str, bytes]:
    fh.seek(offset)
    head = fh.read(_LFH.size)
    (sig, _ver, _flags, method, _t, _d, _crc, csize, _usize,
     nlen, xlen) = _LFH.unpack(head)
    if sig != _LFH_SIG:
        raise ValueError(f"no local file header at offset {offset}")
    name = fh.read(nlen).decode("utf-8")
    fh.read(xlen)
    data = fh.read(csize)
    if method == 0:
        return name, data
    if method == 8:
        return name, zlib.decompress(data, -15)
    if method == 93:
        try:
            import zstandard  # type: ignore
        except ImportError:  # pragma: no cover — depends on the host
            raise ValueError(f"{name!r} is Zstandard-compressed and the "
                             f"'zstandard' package is not installed")
        return name, zstandard.ZstdDecompressor().decompress(data)
    raise ValueError(f"{name!r}: compression method {method} is not one a 3tz allows")


def read_3tz_entry(path: PathLike, name: str) -> Optional[bytes]:
    """The bytes of ``name`` inside the archive, found through the index (binary
    search on the MD5, collisions resolved by the header's file name), or None
    when it is not there. Nothing is extracted."""
    wanted = normalize_path(name)
    digest = hashlib.md5(wanted.encode("utf-8")).digest()
    index = read_3tz_index(path)
    keys = [md5_key(d) for d, _ in index]
    i = bisect_left(keys, md5_key(digest))
    with open(path, "rb") as fh:
        while i < len(index) and index[i][0] == digest:
            found, data = _read_member_at(fh, index[i][1])
            if found == wanted:
                return data
            i += 1
    return None


def index_is_sorted(path: PathLike) -> bool:
    keys = [md5_key(d) for d, _ in read_3tz_index(path)]
    return keys == sorted(keys)


#: The ONE .3tz profile (E.D., 30 Sep 2026): the archive 3DSC writes. MEASURED
#: on ``3D-survey-collection/cesium_exporter/archive_3tz.py`` (3DSC commit
#: ``1430128``, branch ``3DSC-dev-1.7.0``, file sha256 ``3309db81…``), whose
#: ``write_3tz(src_dir, out_path)`` with its default ``compress=False`` writes:
#:
#: * members in path order (``list_entries`` sorts), the index LAST;
#: * every entry — the index too — dated 1980-01-01 00:00:00 (``FIXED_DATE``);
#: * every entry STORED (``compress=True`` exists there and is NOT this profile:
#:   a deflate stream depends on the compressor);
#: * ``create_system`` 3 (unix, whatever the host) and ``external_attr``
#:   ``0o100644 << 16``, every entry the index included (``_zinfo``);
#: * no extra field (zip64 only for an entry of 4 GB or more: ``allowZip64`` and
#:   ``force_zip64=size >= 0xFFFFFFFF``);
#: * general purpose flags 0 on an ASCII name and ``0x800`` (bit 11, «the name
#:   is UTF-8») on a non-ASCII one, and nothing else: it is what Python's
#:   ``zipfile`` writes, and it depends on the name alone (E.D., 30 Sep 2026;
#:   MEASURED 22 Oct 2026: until then this profile asked flags 0 everywhere and
#:   called 3DSC's own archive of ``Data/città.b3dm`` not canonical);
#: * every name in Unicode NFC: macOS hands names over in NFD, and without
#:   normalising the same folder gives one sha256 on a Mac and another on Linux
#:   or Windows (3DSC normalises from 22 Oct 2026);
#: * ``.DS_Store`` and ``Thumbs.db`` never packed (``SKIP_NAMES``);
#: * ``tileset.json`` at the root, no ``.3tz`` in any path.
#:
#: The source text of the profile is ``dtcstamp/profiles/3tz.md``; this
#: constant and ``dtcstamp.CANONICAL_3TZ`` say the same thing.
#:
#: MEASURED on the base TempluMare (``_base_EMStudio/RM/TempluMare_cesium.3tz``,
#: 199 378 562 B, sha256 ``232dfcbc148f30e5…``): 7303 entries, all of the above
#: (and ``create_version`` 20, which Python's zipfile writes and 3DSC does not
#: set: reported, not required).
CANONICAL_3TZ_PROFILE: Dict[str, object] = {
    "source": "3D-survey-collection/cesium_exporter/archive_3tz.py",
    "source_commit": "1430128",
    "date_time": (1980, 1, 1, 0, 0, 0),
    "compress_type": zipfile.ZIP_STORED,
    "create_system": 3,
    "external_attr": 0o100644 << 16,
    "flag_bits_ascii": 0,
    "flag_bits_non_ascii": 0x800,
    "name_form": "NFC",
    "skip_names": (".DS_Store", "Thumbs.db"),
    "profile_text": "dtcstamp/profiles/3tz.md",
}

_ZIP64_LIMIT = 0xFFFFFFFF


def _needs_zip64(info: zipfile.ZipInfo) -> bool:
    return max(info.file_size, info.compress_size, info.header_offset) >= _ZIP64_LIMIT


def _expected_flags(name: str) -> int:
    prof = CANONICAL_3TZ_PROFILE
    return prof["flag_bits_ascii"] if name.isascii() else prof["flag_bits_non_ascii"]


def is_canonical_3tz(path: PathLike) -> Dict[str, object]:
    """Whether the archive follows :data:`CANONICAL_3TZ_PROFILE` — 3DSC's —
    criterion by criterion, with the reasons when it does not.

    Returns ``{criterion: bool…, "canonical": bool, "reasons": [str…],
    "members": n, "dates": […], "methods": […], "create_versions": […]}``.
    The criteria: ``entries_in_order``, ``index_last``, ``index_sorted``,
    ``fixed_dates``, ``stored``, ``create_system``, ``external_attr``,
    ``no_extra_fields``, ``flags`` (0 on an ASCII name, 0x800 on a non-ASCII
    one), ``names_nfc``, ``tileset_at_root``, ``no_3tz_paths``,
    ``no_skipped_names``.

    MEASURED (20 Oct 2026): the base TempluMare 3tz is canonical; a 3tz written
    by 3d-tiles-tools 0.5.4 is NOT, for two reasons: every entry carries the
    time of writing (two conversions of the same folder, two digests: the one
    that makes its digest name the moment and not the content), and its file
    attributes carry the DOS archive bit (``0x81a40020``, not ``0x81a40000``).
    It is also written with ``create_version`` 45 (reported, not required).
    """
    prof = CANONICAL_3TZ_PROFILE
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
    members = [i for i in infos if i.filename != INDEX_NAME]
    names = [i.filename for i in members]
    index_last = bool(infos) and infos[-1].filename == INDEX_NAME
    try:
        index_sorted = index_last and index_is_sorted(path)
    except ValueError:
        index_sorted = False
    checks = {
        "entries_in_order": [n.encode("utf-8") for n in names]
                            == sorted(n.encode("utf-8") for n in names),
        "index_last": index_last,
        "index_sorted": index_sorted,
        "fixed_dates": all(i.date_time == prof["date_time"] for i in infos),
        "stored": all(i.compress_type == prof["compress_type"] for i in infos),
        "create_system": all(i.create_system == prof["create_system"] for i in infos),
        "external_attr": all(i.external_attr == prof["external_attr"] for i in infos),
        "no_extra_fields": all(not i.extra or _needs_zip64(i) for i in infos),
        "flags": all(i.flag_bits == _expected_flags(i.filename) for i in infos),
        "names_nfc": all(unicodedata.normalize(prof["name_form"], i.filename)
                         == i.filename for i in infos),
        "tileset_at_root": "tileset.json" in names,
        "no_3tz_paths": not any(".3tz" in n.lower() for n in names),
        "no_skipped_names": not any(n.rsplit("/", 1)[-1] in prof["skip_names"]
                                    for n in names),
    }
    why = {
        "entries_in_order": "members are not in path order",
        "index_last": f"{INDEX_NAME} is not the last entry",
        "index_sorted": "the index is not sorted by MD5",
        "fixed_dates": "entries carry a date other than 1980-01-01 00:00:00 "
                       "(the time of writing: the digest names the moment of "
                       "packing, not the content)",
        "stored": "entries are compressed",
        "create_system": "create_system is not 3 (unix)",
        "external_attr": "file attributes are not 0o100644",
        "no_extra_fields": "entries carry extra fields",
        "flags": "general purpose flags other than 0 on an ASCII name and "
                 "0x800 on a non-ASCII one",
        "names_nfc": "names are not in Unicode NFC (a name as macOS gives it, "
                     "NFD: the same folder would give another sha256 elsewhere)",
        "tileset_at_root": "no tileset.json at the root",
        "no_3tz_paths": "a path contains '.3tz'",
        "no_skipped_names": ".DS_Store / Thumbs.db are packed",
    }
    reasons = [why[k] for k, ok in checks.items() if not ok]
    if not checks["fixed_dates"]:
        seen = sorted({i.date_time for i in infos} - {prof["date_time"]})
        reasons[reasons.index(why["fixed_dates"])] += f": {seen[:3]}"
    if not checks["external_attr"]:
        seen = sorted({hex(i.external_attr) for i in infos}
                      - {hex(prof["external_attr"])})
        reasons[reasons.index(why["external_attr"])] += \
            f": {seen[:3]}, not {hex(prof['external_attr'])}"
    if not checks["names_nfc"]:
        seen = [i.filename for i in infos
                if unicodedata.normalize(prof["name_form"], i.filename) != i.filename]
        reasons[reasons.index(why["names_nfc"])] += f": {seen[:3]}"
    if not checks["flags"]:
        seen = [(i.filename, hex(i.flag_bits)) for i in infos
                if i.flag_bits != _expected_flags(i.filename)]
        reasons[reasons.index(why["flags"])] += f": {seen[:3]}"
    return {**checks, "canonical": not reasons, "reasons": reasons,
            "members": len(members),
            "dates": sorted({i.date_time for i in infos})[:3],
            "methods": sorted({i.compress_type for i in infos}),
            "create_versions": sorted({i.create_version for i in infos})}
