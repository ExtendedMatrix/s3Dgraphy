"""The MASTER and its stamp — one answer for EMStudio, EM Tools and 3DSC
(MICRO-TIMBRA-MASTER, 6 Nov 2026, on E.D.'s «Timbrare i master, e due tipi di
master», 30 Oct 2026).

A master is the source the others are made FROM (``ResourceNode.TIERS``);
what holds is the stamped FILE outside the ``.blend`` (the .blend is a cache,
brain: *Blender come cache di EMStudio*). So every tool shows, beside a master
as it arrives, whether it is stamped, and offers the gesture that stamps it.
The questions are asked here, once:

* :func:`master_kind` — **very high resolution** (dense geometry, often with
  no texture) or **complete** (textured). The declared kind wins
  (``data.master_kind``, :attr:`ResourceNode.MASTER_KINDS`); otherwise the
  textures decide, and nothing is said when they are not known;
* :func:`is_textured` — whether a mesh file calls images (an OBJ's ``map_*``,
  a glTF's ``images``, a PLY's ``TextureFile``). Vertex colours are not a
  texture: a coloured VHR PLY stays very high resolution;
* :func:`looks_like_master` — a 3D file a tool should treat as a master: the
  graph says ``tier: master``, or it sits in a ``master/`` folder (the
  convention of the design), or its name says it;
* :func:`stamp_state` — ``unstamped``, ``stamped``, ``changed_after_stamp``
  (the bytes are not the ones the stamp names: «modificato dopo il timbro»)
  or ``unverified`` (a stamp is there and the bytes were not hashed now);
* :func:`mark` — the sign a row draws: «⚠ master not stamped · very high
  resolution» with the gesture ``stamp_master``, or «✔ master stamped».

Standard library and dtcstamp only: EM Tools and 3DSC call it inside Blender.
"""

from __future__ import annotations

import json
import os
import re
import struct
from datetime import datetime
from typing import Any, Callable, Dict, Optional

#: the two kinds of master (E.D., 30 Oct 2026) — the same tuple as
#: ``ResourceNode.MASTER_KINDS`` (asserted by the tests)
VERY_HIGH_RESOLUTION = "very_high_resolution"
COMPLETE = "complete"
MASTER_KINDS = (VERY_HIGH_RESOLUTION, COMPLETE)

#: what the rows say, in English; the interfaces translate (datamodel
#: translations, section ``master_kinds``)
KIND_LABELS = {VERY_HIGH_RESOLUTION: "very high resolution", COMPLETE: "complete"}

#: the states of a master's stamp, with their signs
STATES = {
    "unstamped": "⚠",            # no stamp beside it: the gesture is «Stamp»
    "changed_after_stamp": "⚠",  # a stamp, and the bytes are not the ones it names
    "unverified": "◐",           # a stamp, the bytes not hashed now
    "stamped": "✔",
}
#: the gesture each state proposes
GESTURES = {"unstamped": "stamp_master", "changed_after_stamp": "stamp_master_revision",
            "unverified": "verify", "stamped": None}

#: 3D files a master can be (meshes, and the dense clouds a VHR often is)
MODEL_EXTENSIONS = (".obj", ".ply", ".glb", ".gltf", ".fbx", ".stl", ".dae", ".abc",
                    ".usd", ".usdz", ".usdc", ".x3d", ".wrl", ".e57", ".las", ".laz", ".pts", ".xyz")
#: folder names that hold masters (``SB/<Container>/master/``, ``_master/<Container>/``)
MASTER_FOLDERS = ("master", "_master", "masters")
_NAME_RE = re.compile(r"(^|[^a-z])(master|vhr|highres|hi-?res|very[_ -]?high)([^a-z]|$)", re.I)

STAMP_SUFFIX = ".stamp.json"


def _dtc():
    import dtcstamp  # the bundle's: s3dgraphy requires it
    return dtcstamp


# ── the kind ────────────────────────────────────────────────────────────────

def master_kind(declared: Any = None, *, textured: Optional[bool] = None) -> Optional[str]:
    """The kind of a master: the declared one when it is a word of the
    vocabulary; else ``complete`` for a textured mesh, ``very_high_resolution``
    for one without texture; ``None`` when neither is known (nothing invented)."""
    d = str(declared or "").strip()
    if d in MASTER_KINDS:
        return d
    if textured is True:
        return COMPLETE
    if textured is False:
        return VERY_HIGH_RESOLUTION
    return None


def _obj_textured(path: str) -> Optional[bool]:
    base = os.path.dirname(path)
    mtls = []
    with open(path, "rb") as fh:
        for i, line in enumerate(fh):
            if line.startswith(b"mtllib"):
                mtls.append(line[6:].strip().decode("utf-8", "replace"))
            elif line.startswith((b"v ", b"f ")) and i > 200000:
                break  # the header is read; a 1 GB body is not
    if not mtls:
        return False
    seen = False
    for m in mtls:
        p = os.path.join(base, m)
        if not os.path.isfile(p):
            continue
        seen = True
        with open(p, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if re.match(r"\s*map_(Kd|Ka|Ks|d|bump|Bump)\b", line):
                    return True
    return False if seen else None


def _gltf_json(path: str) -> Optional[Dict[str, Any]]:
    with open(path, "rb") as fh:
        head = fh.read(12)
        if head[:4] == b"glTF":
            n, kind = struct.unpack("<II", fh.read(8))
            if kind != 0x4E4F534A:
                return None
            return json.loads(fh.read(n))
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _ply_textured(path: str) -> Optional[bool]:
    with open(path, "rb") as fh:
        for _ in range(200):
            line = fh.readline()
            if not line:
                break
            low = line.strip().lower()
            if low.startswith(b"comment texturefile") or b"texcoord" in low:
                return True
            if low == b"end_header":
                return False
    return None


def is_textured(path: str) -> Optional[bool]:
    """Whether a mesh file carries a texture; ``None`` when the format is not
    read here or the file cannot be read."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".obj":
            return _obj_textured(path)
        if ext in (".glb", ".gltf"):
            doc = _gltf_json(path)
            return None if doc is None else bool(doc.get("images") or doc.get("textures"))
        if ext == ".ply":
            return _ply_textured(path)
        if ext in (".e57", ".las", ".laz", ".pts", ".xyz"):
            return False  # a cloud has no texture: a VHR when it is a master
    except (OSError, ValueError, struct.error):
        return None
    return None


# ── which files are masters ─────────────────────────────────────────────────

def is_model(path: str) -> bool:
    return os.path.splitext(str(path or ""))[1].lower() in MODEL_EXTENSIONS


def looks_like_master(path: str, *, tier: Optional[str] = None) -> bool:
    """A 3D file a tool should treat as a master: ``tier: master`` in the
    graph, or a ``master/`` folder on its path, or a name that says it
    (``…_master.obj``, ``…_VHR.ply``, ``…_highres.obj``). A version
    (``tier: distribution``) never is."""
    if tier == "distribution" or not is_model(path):
        return False
    if tier == "master":
        return True
    parts = [p.lower() for p in re.split(r"[\\/]+", str(path))]
    if any(p in MASTER_FOLDERS for p in parts[:-1]):
        return True
    stem = os.path.splitext(parts[-1])[0] if parts else ""
    return bool(_NAME_RE.search(stem)) and "@" not in stem


# ── the stamp of a master ───────────────────────────────────────────────────

def stamp_path_for(path: str) -> str:
    """``<file>.stamp.json`` beside it (dtcstamp's name for the asset)."""
    path = os.path.abspath(str(path).rstrip("/\\"))
    return os.path.join(os.path.dirname(path),
                        _dtc().stamp_filename({}, asset=os.path.basename(path)))


def _when(text: Any) -> Optional[float]:
    s = str(text or "").strip()
    if not s:
        return None
    try:
        if len(s) == 10:
            return datetime.strptime(s, "%Y-%m-%d").timestamp()
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def stamp_state(path: str, *, stamp: Optional[Dict[str, Any]] = None, sha_now: Optional[str] = None,
                hash_now: bool = False, hasher: Optional[Callable[[str], str]] = None) -> Dict[str, Any]:
    """Whether the master at ``path`` is stamped, and whether its bytes are
    still the ones the stamp names.

    ``stamp``: the stamp when the caller has it, else ``<path>.stamp.json`` is
    read. ``sha_now``: the file's sha256 when the caller knows it (a cache);
    ``hash_now``: hash it here (dtcstamp: a file, the members of a file set,
    the content of a folder). Without either, a stamp whose file was modified
    after it is ``unverified`` with the reason said.

    → ``{state, sign, gesture, at, digest, why}``."""
    out: Dict[str, Any] = {"state": "unstamped", "at": None, "digest": None, "why": ""}
    if stamp is None:
        sp = stamp_path_for(path)
        if os.path.isfile(sp):
            try:
                stamp = _dtc().read_stamp(sp)
            except Exception as exc:  # noqa: BLE001 — unreadable is unstamped, said
                out["why"] = f"the stamp beside it cannot be read ({exc})"
                stamp = None
    if not stamp:
        out["why"] = out["why"] or "no stamp beside the file"
        return _signed(out)
    me = stamp.get("self") or {}
    out["at"] = (stamp.get("by") or {}).get("at")
    out["digest"] = me.get("digest")
    out["resource_id"] = me.get("resource_id")
    want = str(me.get("digest") or "")
    covers = me.get("digest_covers") or "artifact"
    have: Optional[str] = None
    if sha_now:
        have = sha_now if str(sha_now).startswith("sha256:") else "sha256:" + str(sha_now)
    elif hash_now and os.path.exists(path):
        dtc = _dtc()
        try:
            if os.path.isdir(path):
                have = dtc.content_digest(path, entry_point=None)
            elif covers == "members":
                have = dtc.members_digest(dtc.follow_references(path)["members"])
            else:
                have = (hasher or dtc.file_digest)(path)
        except Exception as exc:  # noqa: BLE001
            out["why"] = f"cannot be hashed ({exc})"
    if want and have:
        if have == want:
            out["state"], out["why"] = "stamped", "the bytes are the ones the stamp names"
        else:
            out["state"], out["why"] = "changed_after_stamp", "the bytes are not the ones the stamp names"
        return _signed(out)
    stamped_at = _when(out["at"])
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    # a stamp's time has the second (a date only: the day) — a file written in
    # the same second, or that day, is not «after»
    margin = 86400 if len(str(out["at"])) == 10 else 2
    if stamped_at is not None and mtime is not None and mtime > stamped_at + margin:
        out["state"] = "unverified"
        out["why"] = "the file was modified after its stamp: hash it to know"
        return _signed(out)
    out["state"], out["why"] = "stamped", out["why"] or "stamped (not hashed now)"
    return _signed(out)


def _signed(out: Dict[str, Any]) -> Dict[str, Any]:
    out["sign"] = STATES[out["state"]]
    out["gesture"] = GESTURES[out["state"]]
    return out


def mark(path: str, *, tier: Optional[str] = None, declared_kind: Any = None,
         state: Optional[Dict[str, Any]] = None, textured: Optional[bool] = None,
         hash_now: bool = False) -> Optional[Dict[str, Any]]:
    """The sign a row draws beside a file, or ``None`` when it is not a master.

    → ``{master, kind, kind_label, state, sign, gesture, label, why, at}``;
    ``label`` is the sentence in English («master not stamped · very high
    resolution»)."""
    if not looks_like_master(path, tier=tier):
        return None
    st = state or stamp_state(path, hash_now=hash_now)
    if textured is None and master_kind(declared_kind) is None:
        textured = is_textured(path)
    kind = master_kind(declared_kind, textured=textured)
    head = {"unstamped": "master not stamped", "changed_after_stamp": "master changed after its stamp",
            "unverified": "master stamped, modified after", "stamped": "master stamped"}[st["state"]]
    label = head + (f" · {KIND_LABELS[kind]}" if kind else "")
    return {"master": True, "kind": kind, "kind_label": KIND_LABELS.get(kind or ""), "state": st["state"],
            "sign": st["sign"], "gesture": st["gesture"], "label": label, "why": st.get("why", ""),
            "at": st.get("at"), "digest": st.get("digest")}


def to_stamp(stamp: Dict[str, Any], kind: Optional[str]) -> Dict[str, Any]:
    """Write the master's kind on a stamp being made: ``self.tier: master``
    and ``self.master_kind`` (additive fields, kept by every reader — the
    format's rule «keep the fields you do not understand»)."""
    me = stamp.setdefault("self", {})
    me["tier"] = "master"
    if kind in MASTER_KINDS:
        me["master_kind"] = kind
    return stamp


# ── the radar's gesture, in the graph: a new version OF THE MASTER ──────────

def register_master_revision(graph: Any, old_id: str, *, name: str,
                             files: Any, checksum: str = "",
                             master_kind: Optional[str] = None,
                             technique: str = "manual work in Blender",
                             software: Optional[Any] = None,
                             author: Optional[str] = None, at: Optional[str] = None,
                             resource_id: Optional[str] = None) -> Dict[str, Any]:
    """«Export as a new version of the master» (MICRO-TIMBRA-MASTER p.3), the
    graph's half: a NEW master resource for the file just exported and
    stamped, ``was_revision_of`` the master it replaces (newer → older, the
    edge resources use), DERIVED from it by one step (the work done on it in
    Blender: ``transformation`` with ``technique``), and the representation
    models that hatted the old master now hat the new one — the old stays as
    history, with the versions born from it. The .blend is never involved:
    it is a cache.

    → ``{resource_id, old_id, process_id, moved: [rm ids], master_kind}``."""
    from .files import add_resource
    from ..dtc.ingest import declare_derivation
    old = graph.find_node_by_id(old_id)
    if old is None:
        raise ValueError(f"{old_id!r} is not in this graph")
    od = getattr(old, "data", None) or {}
    if od.get("tier") == "distribution":
        raise ValueError(f"{old_id!r} is a distribution: a version, not a master")
    kind = master_kind if master_kind in MASTER_KINDS else (od.get("master_kind") or None)
    data: Dict[str, Any] = {}
    if kind:
        data["master_kind"] = kind
    node = add_resource(graph, name=name, kind=od.get("url_type") or "3d_model", files=list(files or []),
                        tier="master", residency="resident", resource_id=resource_id,
                        data=data or None)
    new_id = node.node_id
    if checksum and not (node.data or {}).get("checksum"):
        node.data["checksum"] = checksum
    graph.add_edge(edge_id=f"{new_id}__was_revision_of__{old_id}", edge_source=new_id,
                   edge_target=old_id, edge_type="was_revision_of")
    res = declare_derivation(graph, new_id, [old_id], dtc_kind="transformation",
                             technique=technique, software=list(software or []) or None,
                             name=f"{technique} · {name}", author=author, at=at)
    moved = []
    for e in list(graph.edges):
        if e.edge_type == "has_linked_resource" and e.edge_target == old_id:
            src = e.edge_source
            graph.remove_edge(e.edge_id)
            graph.add_edge(edge_id=f"{src}_has_linked_resource_{new_id}", edge_source=src,
                           edge_target=new_id, edge_type="has_linked_resource")
            moved.append(src)
    return {"resource_id": new_id, "old_id": old_id, "process_id": res.get("process_id"),
            "moved": moved, "master_kind": kind}
