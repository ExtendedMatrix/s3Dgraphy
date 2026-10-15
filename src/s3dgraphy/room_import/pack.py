"""`--pack-tilesets 3tz` · a tileset folder goes up as ONE canonical `.3tz`.

A tileset in a folder is thousands of files (7302 for Templu Mare); as a
canonical `.3tz` it is one, with its index inside, read a piece at a time with
Range. The writer is `dtcstamp.write_canonical_3tz` — the package that owns the
profile writes it; s3Dgraphy stays a READER of `.3tz` (decision of 30 Sep 2026).

In the graph the archive is a SIBLING REPRESENTATION of the folder (the rule of
`resources.files`): a `ResourceNode` with `packaging: archive`,
`dtc_derived_from` the folder, made by a DTC step `packing` with its stamp.
The folder stays, as a reference (E.D., 15 Oct 2026, evening: the two forms
live together in the room).

A sibling the graph ALREADY has is used as it is, when it is the same content
in the canonical form: same content digest as the folder, canonical, and the
sha256 the graph records. Nothing is packed again and nothing is added.
"""

from __future__ import annotations

import datetime
import json
import os
import uuid
from typing import Any, Dict, Optional

from .errors import RoomError

MEDIA_TYPE_3TZ = "application/vnd.maxar.archive.3tz+zip"
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://extendedmatrix.org/s3dgraphy/room-import/pack")


def _dtcstamp():
    import dtcstamp
    if not hasattr(dtcstamp, "write_canonical_3tz"):
        raise RoomError(
            f"dtcstamp {getattr(dtcstamp, '__version__', '?')} has no "
            f"write_canonical_3tz: --pack-tilesets needs the dtcstamp that owns "
            f"the writer (after 0.1.4)")
    return dtcstamp


def _data(node: Any) -> Dict[str, Any]:
    data = getattr(node, "data", None)
    return data if isinstance(data, dict) else {}


def _digest_of(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("digest") or "")
    return str(block or "")


def sibling_archive(graph: Any, dir_id: str) -> Optional[Any]:
    """The `.3tz` the graph already declares for this folder: a resource that
    `dtc_derived_from` it with `packaging: archive` and the 3tz media type (or
    a `.3tz` locator). None when there is none."""
    for edge in getattr(graph, "edges", []) or []:
        if edge.edge_type != "dtc_derived_from" or edge.edge_target != dir_id:
            continue
        node = graph.find_node_by_id(edge.edge_source)
        d = _data(node)
        if node is None or d.get("packaging") != "archive":
            continue
        if d.get("media_type") == MEDIA_TYPE_3TZ or str(d.get("url") or "").lower().endswith(".3tz"):
            return node
    return None


def reusable(sibling: Any, path: Optional[str], folder_digest: str) -> Dict[str, Any]:
    """Whether the sibling on this disk IS the canonical packing of the folder:
    → `{ok, why, canonical, content, sha256}`."""
    S = _dtcstamp()
    if not path or not os.path.isfile(path):
        return {"ok": False, "why": "the archive is not on this disk"}
    verdict = S.is_canonical_3tz(path)
    recorded = _digest_of(_data(sibling).get("content_digest"))
    out = {"canonical": bool(verdict["canonical"]),
           "content": recorded == folder_digest, "sha256": S.file_digest(path)}
    if not out["canonical"]:
        out.update(ok=False, why="not canonical: " + "; ".join(verdict["reasons"]))
    elif not out["content"]:
        out.update(ok=False, why=f"its recorded content {recorded or 'is not said'}, "
                                 f"the folder's {folder_digest}")
    else:
        out.update(ok=True, why="the same content, canonical")
    return out


def pack_tree(graph: Any, dir_node: Any, folder: str, out_dir: str, *,
              when: Optional[str] = None) -> Dict[str, Any]:
    """Pack `folder` (the tree of `dir_node`) into `out_dir`, add the sibling
    archive resource, the DTC step `packing` and the stamp beside the file.

    → `{archive_id, process_id, path, stamp_path, sha256, bytes, entries,
    content_digest, seconds}`. Ids are derived from the folder's resource and
    the archive's digest: a second packing of the same content adds nothing.
    """
    from ..nodes.dtc_process_node import DTCProcessNode
    from ..resources.files import add_resource

    S = _dtcstamp()
    os.makedirs(out_dir, exist_ok=True)
    leaf = os.path.basename(os.path.normpath(folder)) or "tileset"
    out_path = os.path.join(out_dir, f"{leaf}.3tz")
    made = S.write_canonical_3tz(folder, out_path)
    hexd = made["sha256"].split(":", 1)[1]
    stamp_path = out_path + S.STAMP_SUFFIX
    # the same content packed again is the same step: its stamp (and so its
    # time) is kept, and a second run writes, sends and seeds nothing new
    kept = None
    if os.path.isfile(stamp_path):
        try:
            kept = S.read_stamp(stamp_path)
        except Exception:  # noqa: BLE001 — an unreadable stamp is written anew
            kept = None
        if kept is not None and (kept.get("self") or {}).get("digest") != made["sha256"]:
            kept = None
    at = when or ((kept or {}).get("by") or {}).get("at") or \
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = _data(dir_node)
    archive_id = str(uuid.uuid5(_NS, f"archive|{dir_node.node_id}|{hexd}"))
    process_id = str(uuid.uuid5(_NS, f"packing|{dir_node.node_id}|{hexd}"))
    content = dict(made["content_digest"])
    recorded = _digest_of(d.get("content_digest"))
    if recorded and recorded != content["digest"]:
        raise RoomError(f"the folder {folder} is not the content its resource "
                        f"records ({recorded}): it packs to {content['digest']}")
    if graph.find_node_by_id(archive_id) is None:
        data = {"url": out_path, "checksum": made["sha256"], "media_type": MEDIA_TYPE_3TZ,
                "content_digest": content,
                "description": (f"The folder {leaf} in one file, packed in the "
                                f"canonical .3tz profile (dtcstamp "
                                f"write_canonical_3tz): the same content digest "
                                f"as the folder.")}
        kind = d.get("url_type")
        add_resource(graph, name=f"{getattr(dir_node, 'name', '') or leaf}, archive (.3tz)",
                     kind=kind if kind else None, packaging="archive",
                     tier=d.get("tier") or None, residency="resident",
                     derived_from=[dir_node.node_id], resource_id=archive_id,
                     size_bytes=made["bytes"], data=data)
    if graph.find_node_by_id(process_id) is None:
        step = DTCProcessNode(process_id, name=f"Packing of {leaf} as .3tz",
                              dtc_kind="packing", data={
                                  "created_at": at, "modified_at": at,
                                  "parameters": {"format": "3tz",
                                                 "profile": "dtcstamp profiles/3tz.md"},
                                  "technique": "canonical 3D Tiles Archive: entries in path "
                                               "order, STORED, fixed dates, NFC names, "
                                               "index last",
                                  "tool": {"name": "dtcstamp.write_canonical_3tz",
                                           "version": getattr(S, "__version__", "")}})
        graph.add_node(step)
    for edge_id, source, target, kind in (
            (f"{process_id}~in~{dir_node.node_id}", process_id, dir_node.node_id, "dtc_had_input"),
            (f"{process_id}~out~{archive_id}", process_id, archive_id, "dtc_had_output")):
        if graph.find_edge_by_id(edge_id) is None:
            graph.add_edge(edge_id, source, target, kind)
    if kept is not None:
        return {"archive_id": archive_id, "process_id": process_id, "path": out_path,
                "stamp_path": stamp_path, "sha256": made["sha256"], "bytes": made["bytes"],
                "entries": made["entries"], "content_digest": content,
                "seconds": made["seconds"]}
    stamp = S.new_tree_stamp(out_path, archive_id, computed_by="producer", **{
        "from": [{"resource_id": dir_node.node_id, "digest": content["digest"],
                  "label": getattr(dir_node, "name", "") or leaf}],
        "how": {"process_id": process_id, "dtc_kind": "packing",
                "parameters": {"format": "3tz", "profile": "dtcstamp profiles/3tz.md"},
                "software": [{"name": "dtcstamp",
                              "version": getattr(S, "__version__", "")}]},
        "by": {"at": at}})
    with open(stamp_path, "w", encoding="utf-8") as fh:
        json.dump(stamp, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    return {"archive_id": archive_id, "process_id": process_id, "path": out_path,
            "stamp_path": stamp_path, "sha256": made["sha256"], "bytes": made["bytes"],
            "entries": made["entries"], "content_digest": content,
            "seconds": made["seconds"]}
