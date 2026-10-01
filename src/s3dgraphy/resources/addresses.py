"""Several addresses for one resource (dev27, A4; E.D. 2026-10-01, *il testo,
la risorsa e la selezione*, «Più risorse per un documento»).

* **The same bytes — the same digest — are ONE resource with several
  addresses**: the same PDF on the disk, on MinIO, on Zenodo. It is redundancy:
  if an address dies, the resource stays.
* **Different manifestations** (the scan and the online transcription, two
  editions) are sister ResourceNodes, each with its digest — as before.
* **An online page without saved bytes** is a reference (``residency:
  reference``) with no digest. :func:`snapshot_uri` downloads it, when somebody
  wants to, and gives it a DATED digest (``checksum`` + ``checksum_at``): a
  page changes, and the digest says of which day it is.

Measured before (2026-10-31): a resource kept ONE locator, ``data.url`` (its
files, :class:`~s3dgraphy.nodes.resource_file_node.ResourceFileNode`, one each);
two copies of the same file were either two ResourceNodes, or — through
``publication.promote_resource`` — one whose ``url`` was OVERWRITTEN by the
store's, the disk path lost.

The form (``data.addresses``)::

    [{"locator": "scans/vitruvio.pdf", "residency": "resident"},
     {"locator": "s3://em/ab12…", "residency": "resident",
      "checked_at": "2026-10-31T09:00:00Z", "ok": true}]

``addresses[0]`` is ``data.url`` (the address a consumer that knows only
``url`` — Heriverse — keeps reading); the list is written only when there is a
second address, so a resource of one address looks as it always did. ``ok`` is
``True`` (reachable at ``checked_at``), ``False`` (dead), absent (never
checked). A dead address is a warning, not an error, while a live one remains;
it is never removed by a check, because «dead today» is a fact with a date.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, List, Optional

ADDRESSES_KEY = "addresses"


class AddressError(ValueError):
    """An address that cannot be added; nothing was written."""


def _data(resource: Any) -> Dict[str, Any]:
    data = getattr(resource, "data", None)
    if not isinstance(data, dict):
        data = {}
        resource.data = data
    return data


def _check_resource(resource: Any) -> None:
    if getattr(resource, "node_type", None) != "resource":
        raise AddressError(
            f"'{getattr(resource, 'node_id', resource)}' is not a ResourceNode: "
            f"addresses are of a resource")


def _normalized_digest(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    return text if ":" in text else f"sha256:{text}"


def addresses(resource: Any) -> List[Dict[str, Any]]:
    """Every address of a resource, ``data.url`` first: ``[{locator, residency,
    checked_at?, ok?, primary}]``. ``[]`` for a resource with no locator. A copy
    of each entry — writing into it changes nothing."""
    data = getattr(resource, "data", None) or {}
    listed = [dict(a) for a in (data.get(ADDRESSES_KEY) or [])
              if isinstance(a, dict) and a.get("locator")]
    url = data.get("url")
    if url and not any(a["locator"] == url for a in listed):
        listed.insert(0, {"locator": url, "residency": data.get("residency")})
    out = []
    for i, a in enumerate(listed):
        if a.get("residency") is None:
            a.pop("residency", None)
        a["primary"] = (a["locator"] == url) if url else (i == 0)
        out.append(a)
    return out


def live_addresses(resource: Any) -> List[Dict[str, Any]]:
    """The addresses not marked dead (reachable, or never checked)."""
    return [a for a in addresses(resource) if a.get("ok") is not False]


def _write(resource: Any, entries: List[Dict[str, Any]]) -> None:
    """Store the list, ``data.url`` first (the RDF projection numbers the
    addresses and reads ``url`` back from the first)."""
    data = _data(resource)
    url = data.get("url")
    entries = sorted(entries, key=lambda a: a.get("locator") != url)
    clean = []
    for a in entries:
        e = {k: v for k, v in a.items() if k != "primary" and v is not None}
        clean.append(e)
    if len(clean) <= 1 and not any(("ok" in e or "checked_at" in e) for e in clean):
        data.pop(ADDRESSES_KEY, None)        # one plain address: data.url says it
    else:
        data[ADDRESSES_KEY] = clean


def add_address(resource: Any, locator: str, *, checksum: Optional[str] = None,
                residency: Optional[str] = None) -> List[Dict[str, Any]]:
    """Add a copy of the SAME bytes at another address.

    ``checksum`` is the digest of the bytes found there: it must be the
    resource's own — same digest, same resource. A different one is another
    manifestation, a sister resource (``add_resource``), and is refused. A
    resource with no digest cannot say that two places hold the same bytes, and
    is refused too (download it first: :func:`snapshot_uri`). A resource with no
    ``url`` takes the locator as its url. Adding an address it already has
    changes nothing. Returns :func:`addresses`."""
    from ..nodes.resource_node import ResourceNode
    _check_resource(resource)
    if not isinstance(locator, str) or not locator.strip():
        raise AddressError("an address needs a locator")
    locator = locator.strip()
    if residency is not None and residency not in ResourceNode.RESIDENCIES:
        raise AddressError(
            f"residency must be one of {list(ResourceNode.RESIDENCIES)}, "
            f"got {residency!r}")
    data = _data(resource)
    current = addresses(resource)
    if any(a["locator"] == locator for a in current):
        return current
    if not data.get("url"):
        data["url"] = locator
        if residency and not data.get("residency"):
            data["residency"] = residency
        return addresses(resource)
    own = _normalized_digest(data.get("checksum"))
    if own is None:
        raise AddressError(
            f"'{resource.node_id}' has no digest: nothing says the bytes at "
            f"{locator!r} are the same. Download it (snapshot_uri) or give it "
            f"its checksum first. Nothing was written.")
    theirs = _normalized_digest(checksum)
    if theirs is None:
        raise AddressError(
            f"the digest of the bytes at {locator!r} is needed: same digest, "
            f"same resource. Nothing was written.")
    if theirs != own:
        raise AddressError(
            f"the bytes at {locator!r} are not the resource's ({theirs} ≠ "
            f"{own}): another manifestation is a sister resource. Nothing was "
            f"written.")
    entry = {"locator": locator}
    if residency:
        entry["residency"] = residency
    _write(resource, current + [entry])
    return addresses(resource)


def check_address(resource: Any, locator: str, *, ok: bool,
                  at: Optional[str] = None) -> Dict[str, Any]:
    """Record whether ``locator`` answered, and when (``ok``, ``checked_at``).
    The address stays either way. Returns ``{address, live, warning}``:
    ``warning`` says when this address is dead, and louder when no live one is
    left."""
    from ..editorial import normalize_instant, now_iso
    _check_resource(resource)
    current = addresses(resource)
    entry = next((a for a in current if a["locator"] == locator), None)
    if entry is None:
        raise AddressError(f"'{resource.node_id}' has no address {locator!r}")
    entry["ok"] = bool(ok)
    entry["checked_at"] = normalize_instant(at) if at else now_iso()
    _write(resource, current)
    live = live_addresses(resource)
    warning = None
    if not ok:
        warning = (f"{locator} did not answer; {len(live)} other address(es) "
                   f"remain" if live else
                   f"{locator} did not answer, and no address of "
                   f"'{resource.node_id}' is left alive")
    return {"address": {k: v for k, v in entry.items() if k != "primary"},
            "live": len(live), "warning": warning}


def _fetch(url: str, timeout: float) -> bytes:
    from .resolver import fetch_bytes
    return fetch_bytes(url, timeout=timeout)


def snapshot_uri(resource: Any, *, at: Optional[str] = None,
                 save_to: Optional[str] = None,
                 fetch: Optional[Callable[[str], bytes]] = None,
                 timeout: float = 30.0) -> Dict[str, Any]:
    """Download the page a reference points at, and give the resource a DATED
    digest: ``checksum`` (``sha256:``) and ``checksum_at``.

    Only for a resource that has no digest yet (one that has bytes already is
    not a snapshot's business: :func:`add_address`). ``save_to`` writes the
    bytes to that path and adds it as a ``resident`` address. ``fetch`` replaces
    the network (a callable ``url -> bytes``), for tests and for a caller that
    has its own client. Returns ``{checksum, checksum_at, size_bytes, saved}``.
    Nothing is written when the download fails (the error is raised)."""
    from ..editorial import normalize_instant, now_iso
    _check_resource(resource)
    data = _data(resource)
    url = data.get("url")
    if not url:
        raise AddressError(f"'{resource.node_id}' has no url to download")
    if data.get("checksum"):
        raise AddressError(
            f"'{resource.node_id}' already has its digest {data['checksum']}: a "
            f"snapshot is for a reference without bytes")
    body = (fetch or (lambda u: _fetch(u, timeout)))(url)
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    when = normalize_instant(at) if at else now_iso()
    data["checksum"] = digest
    data["checksum_at"] = when
    saved = None
    if save_to:
        with open(save_to, "wb") as fh:
            fh.write(body)
        saved = save_to
        add_address(resource, save_to, checksum=digest, residency="resident")
    return {"checksum": digest, "checksum_at": when, "size_bytes": len(body),
            "saved": saved}
