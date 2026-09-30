"""The 3D Tiles Archive (``.3tz``) — read without extracting.

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

Why it is here: for now a tileset is a resource from its ROOT (``tileset.json``,
``packaging: directory``) or from its ZIPPED form (``packaging: archive``, one
file), decided by E.D. on 30 Sep 2026. A 3tz is the zipped form a viewer can
seek into — and whether its digest identifies its CONTENT depends on whether it
was written deterministically, which :func:`is_deterministic_3tz` measures.

Pure Python: ``struct``, ``hashlib``, ``zlib``. Zstandard members need the
``zstandard`` package and say so when it is missing.
"""

from __future__ import annotations

import hashlib
import struct
import zipfile
import zlib
from bisect import bisect_left
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Union

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


def is_deterministic_3tz(path: PathLike) -> Dict[str, object]:
    """Whether the archive's bytes are a function of its CONTENT alone — the
    condition for its digest to identify what is inside and not when or how it
    was packed. Measured, criterion by criterion:

    * ``entries_in_order`` — members in lexicographic order of their names
      (the index last, as the spec wants);
    * ``fixed_dates`` — every member carries the zip epoch, 1980-01-01
      00:00:00, i.e. NO date. One shared date is not enough: MEASURED on
      3d-tiles-tools 0.5.4 (18 Oct 2026), every member carries the moment of
      writing, so two conversions of the same tileset differ in 14 606 bytes
      and in their digest (``single_date`` reports that weaker property);
    * ``uncompressed`` — every member stored (method 0): a deflate stream
      depends on the compressor's version and level;
    * ``no_extra_fields`` — no extra field (they carry mtimes, uid/gid);
    * ``index_sorted`` — the index in the spec's order.

    ``deterministic`` is True only when all of them hold.
    """
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
    members = [i for i in infos if i.filename != INDEX_NAME]
    names = [i.filename for i in members]
    result = {
        "entries_in_order": names == sorted(names)
                            and bool(infos) and infos[-1].filename == INDEX_NAME,
        "fixed_dates": all(i.date_time == _FIXED_DATE for i in infos),
        "single_date": len({i.date_time for i in infos}) <= 1,
        "uncompressed": all(i.compress_type == zipfile.ZIP_STORED for i in infos),
        "no_extra_fields": all(not i.extra for i in infos),
        "index_sorted": index_is_sorted(path),
        "members": len(members),
        "dates": sorted({i.date_time for i in infos})[:3],
        "methods": sorted({i.compress_type for i in infos}),
    }
    result["deterministic"] = all(result[k] for k in (
        "entries_in_order", "fixed_dates", "uncompressed", "no_extra_fields",
        "index_sorted"))
    return result


_FIXED_DATE = (1980, 1, 1, 0, 0, 0)


def _members(source: Union[PathLike, Dict[str, bytes]]) -> List[Tuple[str, bytes]]:
    if isinstance(source, dict):
        items = [(normalize_path(k), v) for k, v in source.items()]
    else:
        root = Path(source)
        items = [(p.relative_to(root).as_posix(), p.read_bytes())
                 for p in root.rglob("*") if p.is_file()]
    return sorted(items)


def write_3tz(target: PathLike, source: Union[PathLike, Dict[str, bytes]], *,
              compress: bool = False) -> Path:
    """Write a 3tz DETERMINISTICALLY: members in name order, one fixed date,
    stored (unless ``compress``), no extra fields, the index last and sorted.

    ``source`` is a directory (its tree becomes the archive) or a dict
    ``{path: bytes}``. Needs ``tileset.json`` at the root. The same content
    gives the same bytes, so the archive's digest identifies its content."""
    members = _members(source)
    if "tileset.json" not in {n for n, _ in members}:
        raise ValueError("a 3tz needs tileset.json at its root")
    if any(".3tz" in n for n, _ in members):
        raise ValueError("a 3tz must not contain '.3tz' in a path (no nesting)")
    target = Path(target)
    method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    offsets: List[Tuple[bytes, int]] = []
    with open(target, "wb") as fh:
        with zipfile.ZipFile(fh, "w") as zf:
            for name, data in members:
                info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
                info.compress_type = method
                info.create_system = 0
                info.external_attr = 0
                offsets.append((hashlib.md5(name.encode("utf-8")).digest(),
                                fh.tell()))
                zf.writestr(info, data)
            offsets.sort(key=lambda e: md5_key(e[0]))
            index = b"".join(d + struct.pack("<Q", off) for d, off in offsets)
            info = zipfile.ZipInfo(INDEX_NAME, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            zf.writestr(info, index)
    return target
