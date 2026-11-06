"""The photogrammetric chain of a Metashape project, stamped WHOLE
(MICRO-TIMBRA-MASTER p.2, 6 Nov 2026, for the dataset of Templu Mare, paper F2).

A format reader like :mod:`.metashape_project` (declared so in
``tests/test_semantic_purity.py``): it reads the project, and writes the
reading as STAMPS where ``metashape_to_dtc`` writes it into a graph.

E.D., 30 Oct 2026: «La catena fotogrammetrica (acquisizione → allineamento →
mesh VHR → riduzione → texturing) deve potersi timbrare per intero.» A stamp
attests ONE step; the chain is what one gets by following the stamps
backwards. So stamping the whole chain is writing ONE stamp PER STEP, each
naming its inputs by identity — and here they are made together, from a
Metashape project read without Metashape
(:func:`s3dgraphy.importer.metashape_project.read_metashape_project`):

1. **acquisition** — one stamp per folder of photographs the chunk uses: the
   image set (``packaging: directory``, the digest of its content), ``from:
   []`` and ``how.dtc_kind: photo`` with the camera in ``how.acquisition``;
2. **alignment** — ``MatchPhotos`` + ``AlignCameras`` + ``OptimizeCameras``:
   the oriented photographs (the ``cameras`` of the chunk), from the image
   sets;
3. **very high resolution mesh** — ``BuildDepthMaps`` + ``BuildModel``: the
   model a reconstruction built, ``self.master_kind: very_high_resolution``;
4. **reduction** — a copy of it with fewer faces (``3DSC LOD0``, a decimation
   Metashape does not log), from the VHR mesh;
5. **texturing** — ``BuildUV`` + ``BuildTexture``: ``self.master_kind:
   complete``, with **two inputs**: the reduced mesh as it was before (the
   stage ``untextured``) and the oriented photographs. Never a linear
   derivative of the VHR.

What the project does not hold is said (``pending``), never invented: a
chunk with no textured model leaves step 5 pending — the complete master is
stamped when it is made. The identities are the graph's
(``metashape_to_dtc``): ``psx:<uuid5 of the locator>``, the stage
``…@untextured``, so the stamps absorbed into a graph meet the nodes the
reader wrote. The assets inside the project are masters (``tier: master``,
``packaging: datablock``); the sha256 of a mesh's data file inside its zip is
``self.content_digest`` (the node's), not ``self.digest``: the bytes a reader
could download are the project, not the mesh.

``by.operator`` is who stamps (an ORCID iD and a name), or absent: the agent
is then the software in ``how`` — the format's rule.
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

STEPS = ("acquisition", "alignment", "mesh_vhr", "reduction", "texturing")
STEP_LABELS = {"acquisition": "acquisition", "alignment": "alignment",
               "mesh_vhr": "very high resolution mesh", "reduction": "reduction",
               "texturing": "texturing"}

_ALIGN = ("MatchPhotos", "AlignCameras", "OptimizeCameras")
_RECONSTRUCT = ("BuildDepthMaps", "BuildPointCloud", "BuildDenseCloud", "BuildModel")


def _dtc():
    # dtcstamp through the library's stamp package: a format reader imports
    # nothing but the stdlib and the library (tests/test_semantic_purity.py)
    from .. import stamp
    return stamp


def _ms():
    from . import metashape_project as MS
    return MS


def _step_of(op) -> Optional[str]:
    MS = _ms()
    if op.dtc_kind == "texturing":
        return "texturing"
    if op.name in _ALIGN:
        return "alignment"
    if op.name in _RECONSTRUCT and op.output.get("type") in ("model", "depth_maps", "point_cloud"):
        return "mesh_vhr"
    if op.name in (MS.LOD0_OPERATION, "copy", "DecimateModel"):
        return "reduction"
    return None


def _key(io: Dict[str, str]) -> tuple:
    return (io.get("type"), io.get("key")) + ((io["stage"],) if io.get("stage") else ())


def photogrammetric_chain(project: Any, *, chunk: Any = None,
                          operator: Optional[Dict[str, Any]] = None,
                          at: Optional[str] = None, digests: bool = True,
                          progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """The stamps of the whole chain of one chunk, in order, not written.

    → ``{chunk, steps: [{step, label, stamp, name, folder, inputs}], pending,
    warnings}``. ``name`` is the file the stamp is written as; ``folder`` where
    it goes (an image set's stamp beside its folder; an asset's beside the
    ``.psx``). ``digests`` False hashes nothing (a dry plan)."""
    MS = _ms()
    dtc = _dtc()
    say = progress or (lambda _m: None)
    target = project.chunk(chunk)
    if target is None:
        raise LookupError(f"no chunk {chunk!r} in this project")
    psx_dir = os.path.dirname(os.path.abspath(project.path))
    software = [{"name": project.software_name or MS.SOFTWARE_FALLBACK,
                 **({"version": project.software_version} if project.software_version else {})}]
    warnings: List[str] = []
    steps: List[Dict[str, Any]] = []
    by: Dict[str, Any] = {}
    if operator:
        by["operator"] = dict(operator)
    by["at"] = at or dtc.now_iso()

    # ── 1 · the image sets, one per folder of photographs ─────────────────
    folders: "OrderedDict[str, List[Any]]" = OrderedDict()
    for p in target.photos:
        if p.resolved:
            folders.setdefault(os.path.dirname(p.resolved), []).append(p)
    sets: List[Dict[str, Any]] = []
    for folder, photos in folders.items():
        here = sum(1 for p in photos if p.exists)
        # the image set is the folder's, not the chunk's: two chunks that use
        # one folder name ONE image set — its id from its content (the bytes
        # decide, as every stamped resource), by name when not hashed
        label = f"photographs {os.path.basename(folder)}"
        rid = "imgset:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "imgset|" + os.path.basename(folder)))
        if not os.path.isdir(folder) or not here:
            warnings.append(f"{label}: the folder is not on this disk ({len(photos)} photographs): "
                            f"declared by name, not stamped")
            sets.append({"resource_id": rid, "label": label, "kind": "declared"})
            continue
        say(f"hashing the image set {os.path.basename(folder)} ({len(photos)} photographs)")
        if digests:
            stamp = dtc.new_tree_stamp(folder, rid, computed_by="stamper", entry_point=None)
        else:
            stamp = {"stamp": dtc.STAMP_VERSION, "self": {"resource_id": rid, "packaging": "directory"}}
        me = stamp["self"]
        if me.get("digest"):
            rid = me["resource_id"] = "res:" + str(me["digest"]).split(":", 1)[-1][:16]
        me["label"] = label
        cams = sorted({" ".join(x for x in (p.make, p.model) if x) for p in photos} - {""})
        acq: Dict[str, Any] = {"in_project": len(photos), "on_disk": here}
        if cams:
            acq["device"] = cams[0] if len(cams) == 1 else cams
        dates = sorted(p.date for p in photos if p.date)
        if dates:
            acq["date_first"], acq["date_last"] = dates[0], dates[-1]
        stamp["from"] = []
        stamp["how"] = {"dtc_kind": "photo", "technique": "photographs for photogrammetry",
                        "acquisition": acq}
        stamp["by"] = dict(by)
        steps.append({"step": "acquisition", "label": label, "stamp": stamp,
                      "name": dtc.stamp_filename(stamp, asset=os.path.basename(folder)),
                      "folder": os.path.dirname(folder), "inputs": []})
        sets.append({"resource_id": rid, "digest": me.get("digest"), "label": label})

    # ── the assets: identities as the graph's reader writes them ──────────
    assets = {(a.type, a.key): a for a in target.assets}
    ident: Dict[tuple, Dict[str, Any]] = {}
    for (t, k), a in assets.items():
        loc = MS.asset_locator(project, target, t, k)
        word = MS.ASSET_WORDS.get(t, (t, None))[0]
        ident[(t, k)] = {"resource_id": MS.asset_id(loc), "locator": loc, "asset": a,
                         "label": f"{target.label} · {a.label or f'{word} {k}'}"}
    for op in target.operations:
        for io in [op.output] + list(op.inputs):
            if io.get("stage") and _key(io) not in ident and (io["type"], io["key"]) in ident:
                base = ident[(io["type"], io["key"])]
                loc = f"{base['locator']}@{io['stage']}"
                ident[_key(io)] = {"resource_id": MS.asset_id(loc), "locator": loc, "asset": None,
                                   "label": f"{base['label']} before texturing"}

    def entry(k: tuple) -> Dict[str, Any]:
        i = ident[k]
        e = {"resource_id": i["resource_id"], "label": i["label"], "tier": "master",
             "packaging": "datablock"}
        return e

    # ── 2–5 · one stamp per step, the operations of a step merged ─────────
    groups: "OrderedDict[tuple, Dict[str, Any]]" = OrderedDict()
    dense: Dict[tuple, Any] = {}
    for op in target.operations:
        step = _step_of(op)
        if step is None:
            if op.output.get("type") not in ("tiled_model",):
                warnings.append(f"{op.name} → {op.output.get('type')} {op.output.get('key')}: "
                                f"not a step of the photogrammetric chain")
            continue
        out = _key(op.output)
        if step == "alignment":
            out = ("cameras", target.frame or "0")  # the tie points are inside the step
        if step == "mesh_vhr" and op.output.get("type") in ("depth_maps", "point_cloud"):
            # the depth maps (a dense cloud) are inside the reconstruction's step
            dense[_key(op.output)] = op
            continue
        g = groups.setdefault((step, out), {"step": step, "output": out, "ops": [], "inputs": []})
        for i in op.inputs:
            if _key(i) in dense and dense[_key(i)] not in g["ops"]:
                g["ops"].append(dense[_key(i)])
        g["ops"].append(op)
        for i in op.inputs:
            k = _key(i)
            if i.get("type") in ("tie_points", "depth_maps"):
                continue  # internal to the step
            if k not in g["inputs"] and k != out:
                g["inputs"].append(k)

    cameras = ("cameras", target.frame or "0")
    for (step, out), g in groups.items():
        if out not in ident:
            warnings.append(f"{step}: its output {out} is not in the project")
            continue
        info = ident[out]
        stamp: Dict[str, Any] = {"stamp": dtc.STAMP_VERSION,
                                 "self": {"resource_id": info["resource_id"], "label": info["label"],
                                          "tier": "master", "packaging": "datablock"}}
        a = info["asset"]
        if a is not None:
            prims = {k: v for k, v in a.counts.items() if k in ("faces", "vertices", "points", "cameras", "aligned")}
            if prims:
                stamp["self"]["measures"] = prims
            if digests and a.data_member and len(out) == 2:
                say(f"hashing {info['label']} ({a.data_member}, {a.data_member_size or 0} bytes in the project)")
                d = MS.member_digest(project, target, a)
                if d:
                    stamp["self"]["content_digest"] = {"digest": d, "files": 1, "computed_by": "stamper"}
        if step == "mesh_vhr" and out[0] == "model":
            stamp["self"]["master_kind"] = "very_high_resolution"
        if step == "texturing":
            stamp["self"]["master_kind"] = "complete"
        if step == "alignment":
            # an image set not on this disk is named by id and label only:
            # an input with no digest, declared
            inputs = [{k: v for k, v in s.items() if k != "kind" and v is not None} for s in sets]
        elif step == "mesh_vhr":
            inputs = [entry(cameras)] if cameras in ident else []
        else:
            inputs = [entry(k) for k in g["inputs"] if k in ident]
        if step == "texturing" and len(inputs) != 2:
            warnings.append(f"texturing of {info['label']}: {len(inputs)} input(s), two expected "
                            f"(the reduced mesh and the oriented photographs)")
        params: Dict[str, Any] = {}
        for op in g["ops"]:
            params.update(op.parameters)
        names = []
        for op in g["ops"]:
            if op.technique and op.technique not in names:
                names.append(op.technique)
        kind = "photogrammetry" if step in ("alignment", "mesh_vhr") else \
            ("texturing" if step == "texturing" else (g["ops"][-1].dtc_kind or "decimation"))
        how: Dict[str, Any] = {"dtc_kind": kind, "technique": " + ".join(names) or step,
                               "software": software}
        if params:
            how["parameters"] = params
        notes = [n for op in g["ops"] for n in op.notes]
        stamp["from"] = inputs
        stamp["how"] = how
        stamp["by"] = dict(by)
        dates = [op.date for op in g["ops"] if op.date]
        if dates:
            stamp["how"]["performed_at"] = max(dates)
        if notes:
            stamp["_notes"] = notes
        steps.append({"step": step, "label": info["label"], "stamp": stamp,
                      "name": dtc.stamp_filename(stamp, asset=_asset_name(info["locator"])),
                      "folder": psx_dir, "inputs": [i["resource_id"] for i in inputs],
                      "locator": info["locator"]})

    done = {s["step"] for s in steps}
    pending = []
    for st in STEPS:
        if st not in done:
            pending.append({"step": st, "label": STEP_LABELS[st],
                            "why": ("the project has no textured model yet: the complete master is "
                                    "stamped when it is made, with two inputs (the reduced mesh and the "
                                    "oriented photographs)") if st == "texturing"
                            else "the project records no such step"})
    order = {s: i for i, s in enumerate(STEPS)}
    steps.sort(key=lambda s: order[s["step"]])
    return {"chunk": {"id": target.id, "label": target.label}, "steps": steps,
            "pending": pending, "warnings": warnings}


def _asset_name(locator: str) -> str:
    """A file name for an asset's stamp: the project's stem, the chunk, the asset."""
    parsed = _dtc().parse_psx_locator(locator.split("@", 1)[0])
    stage = locator.split("@", 1)[1] if "@" in locator else ""
    if not parsed:
        return "asset"
    psx, chunk, word, key = parsed
    stem = os.path.splitext(os.path.basename(psx))[0]
    return f"{stem}#{chunk}#{word}-{key}" + (f"@{stage}" if stage else "")


def write_chain(chain: Dict[str, Any], *, folder: Optional[str] = None) -> List[str]:
    """Write the chain's stamps; → the paths. An existing stamp of the same
    artifact is left as it is (a stamp is never rewritten): its path is
    returned with ``(kept)``. ``folder`` overrides where each one goes."""
    dtc = _dtc()
    out = []
    for s in chain["steps"]:
        where = folder or s["folder"]
        os.makedirs(where, exist_ok=True)
        path = os.path.join(where, s["name"])
        if os.path.exists(path):
            out.append(path + " (kept)")
            continue
        dtc.write_stamp(s["stamp"], path)
        out.append(path)
    return out
