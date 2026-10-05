"""An asset and its versions — one survey object, several levels of detail.

Decided by E.D. (30 Sep 2026, confirmed 3 Oct 2026, «asset padre con le versioni
come risorse figlie»): the ASSET is the master resource (the podium as surveyed,
LOD0), and each VERSION (LOD1, LOD2, a decimated or retopologised mesh) is a
child ``ResourceNode`` made from it:

* ``version ──dtc_derived_from──▶ master``, and a ``DTCProcessNode`` of kind
  ``lod_generation`` with ``dtc_had_input`` the master and ``dtc_had_output`` the
  version — the shape :func:`s3dgraphy.dtc.ingest.declare_derivation` writes;
* the version's LEVEL and PURPOSE go in the process ``parameters`` (``level``,
  ``purpose``), where the ``lod_generation`` kind of the visual rules says the
  level goes; the master's own level, when somebody states it, is the
  ``source_level`` of the same parameters — the level of the input as whoever
  made the version saw it. No new field on the resource, so nothing new to map:
  the parameters of a step already travel in em.json and in RDF;
* the SEMANTIC LINK (the RM or proxy that hats the object, its epochs, its unit)
  is declared ONCE, on the asset. A version inherits it: :func:`inherited_links`
  reads it from the asset, and nothing is copied onto the version — a copy
  would be a second statement that can disagree with the first.

A version whose bytes change is REVISED like any resource (``replace_file``,
``was_revision_of``): the revision keeps the level and purpose of the version it
revises, and :func:`versions_of` answers with the CURRENT revision of each level.

D1 (E.D., 4 Oct 2026; the taxonomy ``TASSONOMIA-TIER-3D.md`` §2) — LEVEL,
USES AND MEASURES:

* the master is ``tier = master`` and has NO level. ``lod0`` is the first
  version derived from it that one can WORK on (textured with the
  Demetrescu-D'Annibale formula: 1.26 mm per texel side, 4096² atlases, UV
  ratio 0.6 — Demetrescu et al. 2026, *Remote Sensing* 18, 203, §2 and §4.7);
  ``lod1 … lodN`` count the ``lod_generation`` steps from LOD0, as 3DSC's LOD
  generator does; a version that only reduces its textures is a ``lodN`` too.
* the level (:data:`LOD_LEVEL_PATTERN`) is an ORDINAL INSIDE ONE CHAIN, and it
  is COMPUTED from the chain (:func:`lod_level_of`), never stored in the graph.
  It is WRITTEN only when something leaves (em.json, a manifest, a record), for
  whoever reads a resource alone, and at load it is computed again and
  COMPARED (:func:`check_lod_levels`), the way a checksum is: a difference is a
  line in the Log. So the reason the measures were chosen over a level
  enumeration still holds — an etiquette must not carry meaning outside its
  chain, and the numbers (:data:`LOD_MEASURES`) are what compares chains.
* the USES (:data:`USES`) are a LIST on the version (``data.use``, beside its
  ``tier``): one version can serve the browser and the engine. The older single
  ``purpose`` of the step is read as a one-item list when it is one of them.
  The MEASURES (:data:`LOD_MEASURES`) are the version's data too.
* engines' automatic LOD (Nanite) is one more way to SHOW a version: it adds to
  the chain LOD1…N and does not replace it — no branch here skips a level for it.

The ``level`` a person gives to :func:`add_version` («LOD1») stays the NAME of
the version and the key of its id; when it is not given, it is the computed one.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Sequence

from .files import (_data, _is_resource, _node, add_resource, resource_files,
                    revisions_of)

#: The computed level of a version: ``lod0`` (the first workable version), ``lod1``…
LOD_LEVEL_PATTERN = r"^lod(0|[1-9][0-9]*)$"

#: What a version is FOR — a list on each version (taxonomy §2b; correspondences
#: with Smithsonian Voyager and 3D Tiles in the datamodel's ``_note``).
#: ``heriverse`` and ``aton`` (datamodel 1.6.26, H4, E.D. 5 Oct 2026): a version
#: made FOR a viewer — the package on disk Heriverse, or another ATON app, opens
#: offline; such a viewer asks :data:`VIEWER_USES`.
USES = ("analysis", "realtime", "web", "mobile_ar", "print", "render", "preview",
        "heriverse", "aton")

#: The uses Heriverse asks for, IN ORDER: the version made for it, then one made
#: for any ATON app, then any web version, then a realtime one (H2, H4).
VIEWER_USES = ("heriverse", "aton", "web", "realtime")

#: The numbers measured on a version when it is born (EMtools): what compares
#: chains. ``tris_per_m2`` is a measure without a target; ``texel_density_dd`` is
#: the texel SIDE in mm in the form of the Demetrescu-D'Annibale formula
#: (reference 1.26); ``geometric_error_m`` is for a 3D Tiles tileset only.
LOD_MEASURES = ("tris_per_m2", "texel_density_dd", "texture_count",
                "texture_side_px", "uv_ratio", "reduction_from_lod0",
                "geometric_error_m")
#: The reference of the formula (Demetrescu et al. 2026, Eq. 1): mm per texel side.
TEXEL_DENSITY_DD_REFERENCE = 1.26

DTC_KIND = "lod_generation"
EDGE_HAD_INPUT = "dtc_had_input"
EDGE_HAD_OUTPUT = "dtc_had_output"
EDGE_HAS_LINKED = "has_linked_resource"

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://extendedmatrix.org/s3dgraphy/asset-version")


def version_id_for(asset_id: str, level: str) -> str:
    """The id of the version of ``asset_id`` at ``level``: derived, so adding
    the same level twice lands on the same node."""
    return str(uuid.uuid5(_NS, f"version|{asset_id}|{_level(level)}"))


def _level(level: Any) -> str:
    text = str(level or "").strip()
    if not text:
        raise ValueError("a version needs a level (for instance «LOD1»)")
    return text


def _level_key(level: Optional[str]):
    """Natural order: LOD2 before LOD10, a level without a number last."""
    text = str(level or "")
    m = re.search(r"(\d+)", text)
    return (0 if m else 1, int(m.group(1)) if m else 0, text)


def _lod_process_of(graph, res_id: str):
    """The ``lod_generation`` step that made ``res_id``, with its input, or
    ``(None, None)``."""
    for e in graph.edges:
        if e.edge_type != EDGE_HAD_OUTPUT or e.edge_target != res_id:
            continue
        proc = _node(graph, e.edge_source)
        if proc is None or _data(proc).get("dtc_kind") != DTC_KIND:
            continue
        inputs = [x.edge_target for x in graph.edges
                  if x.edge_type == EDGE_HAD_INPUT and x.edge_source == proc.node_id]
        res_inputs = [i for i in inputs
                      if _node(graph, i) is not None and _is_resource(_node(graph, i))]
        return proc, (sorted(res_inputs)[0] if res_inputs else None)
    return None, None


def _origin(graph, res_id: str) -> str:
    """The first resource of the revision chain ``res_id`` is in: the one the
    ``lod_generation`` step was declared on."""
    try:
        return revisions_of(graph, res_id)[0]
    except ValueError:
        return res_id


def asset_of(graph, res_id: str) -> str:
    """The asset (the master) ``res_id`` is a version of — ``res_id`` itself
    when it is not a version. Walks a version of a version up to the master."""
    node = _node(graph, res_id)
    if node is None or not _is_resource(node):
        raise ValueError(f"{res_id!r} is not a resource of this graph")
    seen = set()
    cur = res_id
    while cur not in seen:
        seen.add(cur)
        _proc, source = _lod_process_of(graph, _origin(graph, cur))
        if source is None:
            return _origin(graph, cur)
        cur = source
    raise ValueError(f"the versions of {res_id!r} loop at {cur!r}")


def lod_steps(graph, res_id: str) -> int:
    """How many ``lod_generation`` steps lead from the asset to ``res_id`` (0
    for the asset itself; a revision counts as the version it revises)."""
    steps, seen, cur = 0, set(), res_id
    while cur not in seen:
        seen.add(cur)
        _proc, source = _lod_process_of(graph, _origin(graph, cur))
        if source is None:
            return steps
        steps += 1
        cur = source
    raise ValueError(f"the versions of {res_id!r} loop at {cur!r}")


def lod_level_of(graph, res_id: str) -> Optional[str]:
    """The COMPUTED level of ``res_id``: ``lod<steps-1>``, or None for the asset
    (the master has no level) and for a resource that is not a version."""
    node = _node(graph, res_id)
    if node is None or not _is_resource(node):
        return None
    steps = lod_steps(graph, res_id)
    return f"lod{steps - 1}" if steps > 0 else None


def check_use(use: Any) -> List[str]:
    """``use`` as the list a version carries: each value one of :data:`USES`,
    in the given order, without repeats. Refuses an unknown one by name."""
    if use in (None, "", []):
        return []
    items = [use] if isinstance(use, str) else list(use)
    out: List[str] = []
    for u in items:
        u = str(u).strip()
        if u not in USES:
            raise ValueError(f"{u!r} is not a use (known: {', '.join(USES)})")
        if u not in out:
            out.append(u)
    return out


def check_measures(measures: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The measures of a version, each a non-negative number under one of
    :data:`LOD_MEASURES` (``texture_count``/``texture_side_px`` integers)."""
    out: Dict[str, Any] = {}
    for k, v in (measures or {}).items():
        if k not in LOD_MEASURES:
            raise ValueError(f"{k!r} is not a measure of a version "
                             f"(known: {', '.join(LOD_MEASURES)})")
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{k} must be a number, got {v!r}")
        if v < 0:
            raise ValueError(f"{k} cannot be negative, got {v!r}")
        out[k] = int(v) if k in ("texture_count", "texture_side_px") else v
    return out


def _uses_of(params: Dict[str, Any], data: Optional[Dict[str, Any]] = None) -> List[str]:
    """The uses of a version: its ``data.use``; else its step's single
    ``purpose`` when that is a use (versions made before D1)."""
    use = (data or {}).get("use", params.get("use"))
    if isinstance(use, list):
        return [str(u) for u in use]
    if isinstance(use, str) and use:
        return [use]
    purpose = str(params.get("purpose") or "")
    return [purpose] if purpose in USES else []


def _entry(graph, res_id: str, *, level, purpose, process_id, master: bool,
           origin: str) -> Dict[str, Any]:
    node = _node(graph, res_id)
    d = _data(node)
    try:
        chain = revisions_of(graph, origin)
    except ValueError:
        chain = [origin]
    checksum, url, media = d.get("checksum"), d.get("url"), d.get("media_type")
    if not checksum:
        #: a revision writes its files as nodes: one file (or the entry point)
        #: carries the bytes the version is
        files = resource_files(graph, res_id)
        one = files[0] if len(files) == 1 else next(
            (f for f in files if f["role"] == "entry_point"), None)
        if one is not None:
            fd = _data(one["node"])
            checksum = fd.get("checksum") if len(files) == 1 else checksum
            url = url or fd.get("url")
            media = media or fd.get("media_type")
    measures = {k: d[k] for k in LOD_MEASURES if k in d}
    return {"id": res_id, "name": getattr(node, "name", ""),
            "level": level, "purpose": purpose, "master": master,
            "lod_level": None if master else lod_level_of(graph, origin),
            "measures": measures, "primitives": dict(d.get("primitives") or {}),
            "process_id": process_id, "checksum": checksum or "",
            "url": url or "", "residency": d.get("residency") or "",
            "media_type": media or "", "size_bytes": d.get("size_bytes"),
            "revisions": chain}


def _current(graph, res_id: str) -> str:
    try:
        return revisions_of(graph, res_id)[-1]
    except ValueError:
        return res_id


def versions_of(graph, asset_id: str) -> List[Dict[str, Any]]:
    """The asset and its versions, master first, then by level.

    Each entry: ``{id, name, level, lod_level, use, measures, primitives,
    purpose, master, process_id, checksum, url, residency, media_type,
    size_bytes, revisions}``. ``id`` is the CURRENT revision of the version; ``revisions``
    its chain, oldest first. ``level`` is the name given; ``lod_level`` the
    COMPUTED level (None for the master, D1). The versions of a version (a LOD1
    made from LOD0) are listed too. The master's ``level`` is the
    ``source_level`` its versions declared, or None when nobody said it.
    """
    asset = asset_of(graph, asset_id)
    kids: List[Dict[str, Any]] = []
    master_levels = set()
    for e in graph.edges:
        if e.edge_type != EDGE_HAD_INPUT or e.edge_target != asset:
            continue
        proc = _node(graph, e.edge_source)
        if proc is None or _data(proc).get("dtc_kind") != DTC_KIND:
            continue
        params = _data(proc).get("parameters") or {}
        if params.get("source_level"):
            master_levels.add(str(params["source_level"]))
        for o in graph.edges:
            if o.edge_type != EDGE_HAD_OUTPUT or o.edge_source != proc.node_id:
                continue
            out = _node(graph, o.edge_target)
            if out is None or not _is_resource(out):
                continue
            entry = _entry(graph, _current(graph, out.node_id),
                           level=params.get("level"),
                           purpose=params.get("purpose") or "",
                           process_id=proc.node_id, master=False,
                           origin=out.node_id)
            entry["use"] = _uses_of(params, _data(_node(graph, entry["id"])))
            kids.append(entry)
            # a version of a version: its own versions are the asset's too
            kids.extend(_descendants(graph, out.node_id))
    master_level = sorted(master_levels)[0] if len(master_levels) == 1 else None
    out = [_entry(graph, _current(graph, asset), level=master_level, purpose="",
                  process_id=None, master=True, origin=asset)]
    out[0]["use"] = []
    seen = set()
    unique = []
    for k in kids:
        if k["id"] not in seen:
            seen.add(k["id"])
            unique.append(k)
    out += sorted(unique, key=lambda k: (_level_key(k["lod_level"] or k["level"]),
                                         _level_key(k["level"]), k["id"]))
    return out


def _descendants(graph, res_id: str) -> List[Dict[str, Any]]:
    """The versions made FROM ``res_id`` (a LOD1 from LOD0…), recursively."""
    out: List[Dict[str, Any]] = []
    for rid in revisions_of_safe(graph, res_id):
        for e in graph.edges:
            if e.edge_type != EDGE_HAD_INPUT or e.edge_target != rid:
                continue
            proc = _node(graph, e.edge_source)
            if proc is None or _data(proc).get("dtc_kind") != DTC_KIND:
                continue
            params = _data(proc).get("parameters") or {}
            for o in graph.edges:
                if o.edge_type != EDGE_HAD_OUTPUT or o.edge_source != proc.node_id:
                    continue
                child = _node(graph, o.edge_target)
                if child is None or not _is_resource(child):
                    continue
                entry = _entry(graph, _current(graph, child.node_id),
                               level=params.get("level"),
                               purpose=params.get("purpose") or "",
                               process_id=proc.node_id, master=False,
                               origin=child.node_id)
                entry["use"] = _uses_of(params, _data(_node(graph, entry["id"])))
                out.append(entry)
                out.extend(_descendants(graph, child.node_id))
    return out


def revisions_of_safe(graph, res_id: str) -> List[str]:
    try:
        return list(revisions_of(graph, res_id))
    except ValueError:
        return [res_id]


# ── the level written when something leaves, checked when it comes back ──────

def lod_levels_to_write(graph) -> Dict[str, str]:
    """``{resource id: computed level}`` for every version of the graph — what
    an exporter writes as ``lod_level`` (em.json, manifest, record)."""
    out: Dict[str, str] = {}
    for n in graph.nodes:
        if _is_resource(n):
            lvl = lod_level_of(graph, n.node_id)
            if lvl:
                out[n.node_id] = lvl
    return out


def check_lod_levels(graph, *, written: Optional[Dict[str, str]] = None,
                     forget: bool = True) -> List[str]:
    """Compute the levels again and compare, like a checksum. One sentence per
    disagreement, for the Log:

    * a ``lod_level`` written in the file that is not the chain's (or that
      names a resource the chain says is no version, or is not ``lodN``);
    * two versions of one asset with the SAME geometry (vertices and faces
      both counted and equal) at two levels — «two levels for one mesh», the
      case measured on San Pietro: the «LOD0» published on Zenodo has the lines
      ``v`` and ``f`` of the case study's LOD1.

    ``written`` defaults to the ``data.lod_level`` the nodes carry; with
    ``forget`` (default) that value is removed after the check — the graph in
    memory never holds the level, it computes it."""
    import re as _re
    if written is None:
        written = {}
        for n in graph.nodes:
            d = _data(n)
            if _is_resource(n) and d.get("lod_level"):
                written[n.node_id] = str(d["lod_level"])
    out: List[str] = []
    for rid, said in sorted(written.items()):
        node = _node(graph, rid)
        label = getattr(node, "name", rid) if node is not None else rid
        if not _re.match(LOD_LEVEL_PATTERN, said):
            out.append(f"lod_level of {label!r}: {said!r} is not a level (lod0, lod1…)")
            continue
        got = lod_level_of(graph, rid)
        if got is None:
            out.append(f"lod_level of {label!r}: the file says {said}, but in the chain "
                       f"it is no version (the master has no level)")
        elif got != said:
            out.append(f"lod_level of {label!r}: the file says {said}, the chain says {got}")
    if forget:
        for rid in written:
            node = _node(graph, rid)
            if node is not None:
                _data(node).pop("lod_level", None)
    assets = {asset_of(graph, rid) for rid in lod_levels_to_write(graph)}
    for asset in sorted(assets):
        seen: Dict[tuple, Dict[str, Any]] = {}
        for entry in versions_of(graph, asset):
            prim = entry.get("primitives") or {}
            if not (prim.get("vertices") and prim.get("faces")):
                continue
            key = (prim["vertices"], prim["faces"])
            first = seen.get(key)
            if first is None:
                seen[key] = entry
                continue
            a = first.get("lod_level") or "the master"
            b = entry.get("lod_level") or "the master"
            out.append(f"{first['name']!r} ({a}) and {entry['name']!r} ({b}) have the same "
                       f"geometry ({key[0]} vertices, {key[1]} faces): two levels for one mesh")
    return out


def version_info(graph, res_id: str) -> Optional[Dict[str, Any]]:
    """The entry of :func:`versions_of` ``res_id`` belongs to (any revision of
    it), with ``asset_id``; None when ``res_id`` is neither an asset with
    versions nor a version."""
    asset = asset_of(graph, res_id)
    entries = versions_of(graph, asset)
    if len(entries) == 1:
        return None
    for entry in entries:
        if res_id == entry["id"] or res_id in entry["revisions"]:
            return {**entry, "asset_id": asset}
    return None


# ── the version for a use ────────────────────────────────────────────────────
#
# Decided by E.D. (5 Oct 2026, «Heriverse legge l'em.json e sceglie la
# versione»): nothing is exported for a viewer any more. A client reads the
# study and picks, among the resources hung on a representation model, the one
# to load for what it does. ONE rule, written here and copied by whoever cannot
# call Python (Heriverse, EMStudio): the cases of
# ``JSON_config/version_for_cases.json`` are the contract both sides pass.

#: Why :func:`choose_version` answered what it answered.
CHOICE_REASONS = ("level", "use", "master", "none")


def _lod_ordinal(entry: Dict[str, Any]) -> int:
    m = re.match(LOD_LEVEL_PATTERN, str(entry.get("lod_level") or ""))
    return int(m.group(1)) if m else -1


def _same_level(entry: Dict[str, Any], level: str) -> bool:
    want = str(level).strip().lower()
    return want in (str(entry.get("lod_level") or "").lower(),
                    str(entry.get("level") or "").strip().lower())


def choose_version(entries: Sequence[Dict[str, Any]], use: Any,
                   prefer_level: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The version to load for ``use``, among ``entries`` (as :func:`versions_of`
    gives them: the master and its versions). The rule, in words:

    1. ``use`` is one use or a list of them, tried IN ORDER («web, then
       realtime»): the first use some version declares is the one served;
    2. the candidates are the versions (never the master) whose ``use`` list
       holds it;
    3. if ``prefer_level`` is given and a candidate is at that level (its
       computed ``lod_level``, or the name it was given) that one is taken;
    4. otherwise the LIGHTEST candidate: the highest ``lod_level`` (each step
       from LOD0 is lighter), then the fewest bytes (``size_bytes``, unknown
       after known), then the id — so the answer never depends on order;
    5. no version declares any of the uses → the MASTER, and the answer says
       so (``reason: "master"``, a ``note``): loading it is allowed, keeping
       quiet about it is not;
    6. no entries at all → None.

    Returns ``{entry, reason, use, note}``: ``reason`` one of
    :data:`CHOICE_REASONS`, ``use`` the use that was served (None for the
    master), ``note`` a sentence for a log or ``""``. Pure: no graph, so the
    same table of cases runs in Python and in JS."""
    entries = [e for e in (entries or []) if e]
    if not entries:
        return None
    uses = [use] if isinstance(use, str) else list(use or [])
    for u in uses:
        cands = [e for e in entries if not e.get("master") and u in (e.get("use") or [])]
        if not cands:
            continue
        if prefer_level:
            at = sorted((e for e in cands if _same_level(e, prefer_level)),
                        key=lambda e: str(e.get("id")))
            if at:
                return {"entry": at[0], "reason": "level", "use": u, "note": ""}

        def weight(e):
            size = e.get("size_bytes")
            known = isinstance(size, (int, float)) and not isinstance(size, bool)
            return (-_lod_ordinal(e), 0 if known else 1, size if known else 0,
                    str(e.get("id")))

        best = sorted(cands, key=weight)[0]
        note = (f"no {u} version at {prefer_level}: the lightest {u} version instead"
                if prefer_level else "")
        return {"entry": best, "reason": "use", "use": u, "note": note}
    master = next((e for e in entries if e.get("master")), None)
    asked = ", ".join(uses) or "no use"
    if master is None:
        return {"entry": None, "reason": "none", "use": None,
                "note": f"no version for {asked} and no master"}
    return {"entry": master, "reason": "master", "use": None,
            "note": f"no version for {asked}: the master is loaded"}


def version_for(graph, asset_or_rm_id: str, use: Any,
                prefer_level: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """The resource to load for ``use`` from an asset, a version, or a
    representation model (whose ``has_linked_resource`` resources are read).

    The choice is :func:`choose_version` on :func:`versions_of`; this adds
    ``asset_id`` to the answer. An RM hanging resources of several assets
    offers the versions of all of them, and its master is the first asset's
    (by id), said in the ``note``. None when there is nothing to load."""
    node = _node(graph, asset_or_rm_id)
    if node is None:
        raise ValueError(f"{asset_or_rm_id!r} is not a node of this graph")
    if _is_resource(node):
        starts = [asset_or_rm_id]
    else:
        linked = [e.edge_target for e in graph.edges
                  if e.edge_type == EDGE_HAS_LINKED and e.edge_source == asset_or_rm_id
                  and _node(graph, e.edge_target) is not None
                  and _is_resource(_node(graph, e.edge_target))]
        models = [r for r in linked
                  if _data(_node(graph, r)).get("url_type") == "3d_model"]
        starts = models or linked
    assets = sorted({asset_of(graph, r) for r in starts})
    if not assets:
        return None
    entries: List[Dict[str, Any]] = []
    for a in assets:
        entries += [{**e, "asset_id": a} for e in versions_of(graph, a)]
    choice = choose_version(entries, use, prefer_level)
    if choice is None:
        return None
    if choice["reason"] == "master" and len(assets) > 1:
        choice["note"] += f" (of {assets[0]}, the first of {len(assets)} assets)"
    choice["asset_id"] = (choice["entry"] or {}).get("asset_id", assets[0])
    return choice


def inherited_links(graph, res_id: str) -> Dict[str, Any]:
    """The semantic link of ``res_id``: what hats its ASSET.

    ``{asset_id, inherited, facets: [{id, node_type, name}], binds: [{id,
    node_type, name, via}]}`` — ``facets`` are the nodes that reach the asset
    with ``has_linked_resource`` (the RM, the proxy's shape), ``binds`` what
    those facets are for (epochs, units), read the way
    :func:`s3dgraphy.geometry.store_backed.store_backed_geometry` reads them.
    ``inherited`` is True when ``res_id`` is a version and the link was read on
    its asset."""
    from ..geometry.store_backed import _binds

    asset = asset_of(graph, res_id)
    by_id = {n.node_id: n for n in graph.nodes}
    facets, binds, seen = [], [], set()
    for e in graph.edges:
        if e.edge_type != EDGE_HAS_LINKED or e.edge_target != asset:
            continue
        facet = by_id.get(e.edge_source)
        if facet is None or facet.node_id in seen:
            continue
        seen.add(facet.node_id)
        facets.append({"id": facet.node_id, "name": getattr(facet, "name", ""),
                       "node_type": str(getattr(facet, "node_type", "") or "")})
        for b in _binds(graph, facet.node_id, by_id):
            if b["id"] not in {x["id"] for x in binds}:
                binds.append(b)
    return {"asset_id": asset, "inherited": asset != _origin(graph, res_id),
            "facets": facets, "binds": binds}


def add_version(graph, master_id: str, *, level: Optional[str] = None, purpose: str = "",
                use: Optional[Sequence[str]] = None,
                measures: Optional[Dict[str, Any]] = None,
                files: Sequence[Dict[str, Any]] = (), name: Optional[str] = None,
                master_level: Optional[str] = None,
                technique: Optional[str] = None,
                parameters: Optional[Dict[str, Any]] = None,
                tool: Optional[str] = None,
                software: Optional[Sequence[Dict[str, Any]]] = None,
                residency: Optional[str] = None,
                packaging: Optional[str] = None,
                size_bytes: Optional[int] = None,
                primitives: Optional[Dict[str, int]] = None,
                version_id: Optional[str] = None,
                author: Optional[str] = None,
                at: Optional[str] = None) -> Dict[str, Any]:
    """A new version of the asset ``master_id`` at ``level``, for ``purpose``.

    Writes the version resource (kind of the master, ``tier: distribution``,
    ``files`` as :func:`add_resource` takes them) and the ``lod_generation``
    step from the master to it. Idempotent: the id is derived from (asset,
    level), and adding the same level again with the same bytes changes
    nothing. The same level with OTHER bytes is refused — that is a revision of
    the version (``replace_file``), and the error says so.

    ``master_id`` may itself be a version: a LOD2 decimated from LOD1 is a
    different claim from a LOD2 made from the master, and it is written as it
    is said; :func:`asset_of` walks up to the master either way.

    Returns ``{version_id, process_id, created, asset_id, level, purpose,
    warnings}``.
    """
    from ..dtc.ingest import declare_derivation

    master = _node(graph, master_id)
    if master is None or not _is_resource(master):
        raise ValueError(f"{master_id!r} is not a resource of this graph")
    uses = check_use(use if use is not None else ([purpose] if purpose in USES else None))
    measured = check_measures(measures)
    # D1 · the level, when nobody names it, is the computed one: a version of
    # the master is lod0, a version of lodK is lod(K+1)
    lvl = _level(level or f"lod{lod_steps(graph, master_id)}")
    asset = asset_of(graph, master_id)
    vid = version_id or version_id_for(master_id, lvl)
    for entry in versions_of(graph, asset):
        if entry["level"] == lvl and not entry["master"] \
                and vid not in entry["revisions"]:
            raise ValueError(f"{asset!r} already has a version at {lvl!r} "
                             f"({entry['id']}): replace its file to revise it")
    specs = [dict(f) for f in files or ()]
    node = _node(graph, vid)
    created = node is None
    if node is None:
        # named after the ASSET, not after the version it was made from: a
        # lod2 of a lod1 is «<asset> lod2», not «<asset> lod0 lod1 lod2»
        asset_node = _node(graph, asset)
        add_resource(graph, name=name or f"{getattr(asset_node, 'name', master.name)} {lvl}",
                     kind=_data(master).get("url_type") or "", files=specs,
                     tier="distribution", residency=residency,
                     packaging=packaging, size_bytes=size_bytes,
                     primitives=primitives, resource_id=vid)
    else:
        if not _is_resource(node):
            raise ValueError(f"{vid!r} is a {getattr(node, 'node_type', '?')}, "
                             f"not a resource")
        new_sum = next((s.get("checksum") for s in specs if s.get("checksum")), None)
        old_sum = _data(node).get("checksum")
        if new_sum and old_sum and new_sum != old_sum:
            raise ValueError(f"the version {lvl!r} of {asset!r} holds other bytes "
                             f"({old_sum}): replace its file to revise it")
    # D1 · uses and measures are the VERSION's (beside its tier), not the step's
    vdata = _data(_node(graph, vid))
    if measured:
        vdata.update(measured)
    if uses:
        vdata["use"] = uses
    params = dict(parameters or {})
    params["level"] = lvl
    if purpose:
        params["purpose"] = str(purpose)
    if master_level:
        params["source_level"] = str(master_level).strip()
    step = declare_derivation(
        graph, output=vid, inputs=[master_id], dtc_kind=DTC_KIND,
        process_id=str(uuid.uuid5(_NS, f"lod_generation|{vid}")),
        name=f"LOD generation {lvl} of {master.name}",
        technique=technique, parameters=params, tool=tool,
        software=list(software) if software else None, author=author, at=at)
    return {"version_id": vid, "process_id": step["process_id"],
            "created": created, "asset_id": asset, "level": lvl,
            "lod_level": lod_level_of(graph, vid), "use": uses,
            "measures": measured,
            "purpose": str(purpose or ""), "warnings": step["warnings"]}
