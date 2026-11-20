"""The stamp on a derived artifact — G-5 of the geophysics decisions (MICRO-GEO02, part 0, E.D. 19 Nov 2026).

When a plugin MAKES a file — a PNG from a slice, a cache, a baked drape, a
resampled raster, a glb, an export — the encouraged practice (never an
obligation: SPEC.md of em-profiles, «Good practice — the stamp on derived
artifacts») is to write its **stamp** beside it: the immutable record of one
step in the format of ``dtcstamp`` (``stamp-format.md``) — an agent, a process
and its parameters, the inputs consumed by identity, ONE artifact produced.

One line from a plugin::

    ctx.stamp(png, inputs=[source_file], parameters={"colormap": "viridis"},
              dtc_kind="format_conversion", technique="slice rasterization")

writes ``<png>.stamp.json`` and returns the stamp. The agent is the plugin
(id and version, in ``how.software`` before s3dgraphy's own line): by the
format's rule an absent ``by.operator`` means «the agent is the software named
in ``how``», which is exactly a plugin baking a cache. ``em.stamp(...)`` is the
same for a script, and inside a plugin's command it names the calling plugin
by itself.

Nothing here touches the graph: a stamp is a file next to a file. How it joins
the graph's DTC is the reader's (``s3dgraphy.stamp.absorb``): the inputs are
named by ``resource_id`` and ``digest``, so an input that is a graph's
resource — the file of an acquisition, ``dtc_had_output`` — is cited with ITS
id, and the chain acquisition → resource → derivative reads backwards.
"""
from __future__ import annotations

import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

import dtcstamp

#: the namespace of the identities this helper derives from a digest: the same
#: bytes get the same ``res:`` id on every machine (a cache rebuilt is the same artifact)
_NS = uuid.UUID("7b6f1d1e-5c2a-4f3e-9a51-6e0c8f3f2d47")

PathLike = Union[str, "os.PathLike[str]"]


class StampError(ValueError):
    """What cannot be stamped (no file, an input that names nothing)."""


def resource_id_for(digest: str) -> str:
    """``res:<uuid5 of the digest>`` — the identity a derived file gets when
    nobody gave it one: deterministic, so two bakes of the same bytes agree."""
    return "res:" + str(uuid.uuid5(_NS, str(digest)))


def _s3dgraphy_line() -> Dict[str, Any]:
    from .. import __version__
    return {"name": "s3dgraphy", "version": str(__version__)}


def _agent_line(agent: Any) -> Optional[Dict[str, Any]]:
    """The plugin as software: ``{name, id, version}`` from a Plugin, a Context
    or a mapping; ``None`` when nothing is said."""
    if agent is None:
        return None
    if isinstance(agent, Mapping):
        line = {k: str(v) for k, v in agent.items() if k in ("name", "id", "version", "commit") and v}
    else:
        p = getattr(agent, "_p", agent)           # a Context carries its Plugin
        pid = getattr(p, "id", None)
        if not pid:
            raise StampError(f"the agent {agent!r} names no plugin")
        line = {"name": str(getattr(p, "name", None) or pid), "id": str(pid)}
        if getattr(p, "version", None):
            line["version"] = str(p.version)
    if not line.get("name"):
        line["name"] = line.get("id", "")
    if not line["name"]:
        raise StampError("the agent has neither name nor id")
    return line


def _input_entry(item: Any) -> Dict[str, Any]:
    """An input by IDENTITY: a path is hashed (digest, size, its name as a
    courtesy label); a mapping is taken as it is (a graph resource's
    ``resource_id``, an acquisition with ``kind``); never a path in the stamp."""
    if isinstance(item, Mapping):
        entry = {k: v for k, v in item.items() if v is not None}
        if not (str(entry.get("resource_id") or "").strip() or entry.get("digest")):
            raise StampError(f"an input names nothing: {dict(item)!r}")
        if "resource_id" not in entry:
            entry = {"resource_id": resource_id_for(entry["digest"]), **entry}
        return entry
    path = Path(os.fspath(item))
    if not path.is_file():
        raise StampError(f"the input {path} is not a file")
    digest = dtcstamp.file_digest(str(path))
    return {"resource_id": resource_id_for(digest), "digest": digest,
            "size_bytes": path.stat().st_size, "label": path.name}


def make_stamp(artifact: PathLike, *, agent: Any = None, inputs: Iterable[Any] = (),
               parameters: Optional[Mapping[str, Any]] = None, dtc_kind: str = "transformation",
               technique: Optional[str] = None, process: Optional[str] = None,
               label: Optional[str] = None, description: Optional[str] = None,
               resource_id: Optional[str] = None, operator: Optional[Mapping[str, Any]] = None,
               at: Optional[str] = None, tier: Optional[str] = None,
               software: Iterable[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """The stamp of ``artifact`` as a dict (nothing written). See :func:`stamp_artifact`."""
    path = Path(os.fspath(artifact))
    if not path.is_file():
        raise StampError(f"the artifact {path} is not a file")
    digest = dtcstamp.file_digest(str(path))
    me: Dict[str, Any] = {"resource_id": resource_id or resource_id_for(digest), "digest": digest,
                          "digest_covers": "artifact", "packaging": "file",
                          "measures": {"size_bytes": path.stat().st_size}}
    mime = mimetypes.guess_type(path.name)[0]
    if mime:
        me["media_type"] = mime
    if path.suffix:
        me["format"] = path.suffix.lstrip(".").lower()
    if tier:
        me["tier"] = tier
    if label:
        me["label"] = str(label)
    if description:
        me["description"] = str(description)
    lines: List[Dict[str, Any]] = []
    a = _agent_line(agent)
    if a:
        lines.append(a)
    lines.extend(dict(s) for s in software)
    lines.append(_s3dgraphy_line())
    how: Dict[str, Any] = {"dtc_kind": str(dtc_kind)}
    if process:
        how["process_id"] = str(process)
    if technique:
        how["technique"] = str(technique)
    how["parameters"] = dict(parameters or {})
    how["software"] = lines
    by: Dict[str, Any] = {"at": at or dtcstamp.now_iso()}
    if operator:
        by["operator"] = dict(operator)
    stamp = {"stamp": dtcstamp.STAMP_VERSION, "self": me,
             "from": [_input_entry(i) for i in inputs], "how": how, "by": by}
    return dtcstamp.validate_stamp(stamp)


def stamp_path(artifact: PathLike) -> Path:
    """``<artifact>.stamp.json``, beside it (stamp-format, «Nomi dei file»)."""
    path = Path(os.fspath(artifact))
    return path.with_name(path.name + dtcstamp.STAMP_SUFFIX)


def stamp_artifact(artifact: PathLike, *, agent: Any = None, write: bool = True,
                   **fields: Any) -> Dict[str, Any]:
    """Stamp a file a plugin (or a script) made, in one line.

    ``agent`` — the plugin (a :class:`~s3dgraphy.em.plugins.Plugin`, its
    ``ctx`` or ``{"id", "name", "version"}``); inside a plugin's command, the
    calling plugin when not given. ``inputs`` — paths (hashed) or identities
    (``{"resource_id": …}`` of a graph's resource, ``{"resource_id": …, "kind":
    "acquisition"}``). ``parameters``, ``dtc_kind`` (the vocabulary of
    ``dtc_kinds``: ``format_conversion``, ``transformation``, ``export``…),
    ``technique``, ``label``, ``description``, ``resource_id`` (default: derived
    from the digest), ``operator``, ``at``, ``tier``, ``software`` (more lines).

    Writes ``<artifact>.stamp.json`` (``write=False``: only returns it) and
    returns the stamp. Re-stamping the same bytes writes the same record but
    the instant (the format: the same fact registered twice, deduplicated).

    Raises:
        StampError: the artifact or an input path is not a file, or an input
            names nothing.

    Example:
        >>> import os, tempfile
        >>> folder = tempfile.mkdtemp()
        >>> src, png = os.path.join(folder, "slice.dat"), os.path.join(folder, "slice.png")
        >>> _ = open(src, "wb").write(b"raw")
        >>> _ = open(png, "wb").write(b"picture")
        >>> stamp = em.stamp(png, inputs=[src], parameters={"colormap": "viridis"},
        ...                  dtc_kind="format_conversion",
        ...                  agent={"id": "demo", "name": "Demo", "version": "1.0"})
        >>> stamp["how"]["dtc_kind"], stamp["self"]["format"], len(stamp["from"])
        ('format_conversion', 'png', 1)
        >>> os.path.exists(png + ".stamp.json")
        True
    """
    if agent is None:
        from .plugins import calling_now
        calling = calling_now()
        agent = calling.plugin if calling is not None else None
    stamp = make_stamp(artifact, agent=agent, **fields)
    if write:
        dtcstamp.write_stamp(stamp, str(stamp_path(artifact)))
    return stamp


__all__ = ["StampError", "make_stamp", "stamp_artifact", "stamp_path", "resource_id_for"]
