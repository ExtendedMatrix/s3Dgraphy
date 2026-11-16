"""«Porta dentro…» — the one door files enter a study by.

MICRO-E-PORTA-VERSIONI-COLORI p.1 (E.D., 15–16 Nov 2026). One gesture, one
window behind it, whatever the file: a raster, a vector, a DXF (the GIS of
MICRO-D, :func:`..gis.document.add_gis_document`), a 3D model, a tileset, a
picture. Every file enters as part of a DOCUMENT:

* the **document** — a new ``D.nn`` (the study's next, its title in the
  description) or one already there; several files at once are the sheets /
  models of the same document;
* its **date, ALWAYS** (E.D.): «Quando è stato fatto questo documento?» —
  ``data.absolute_time_start``, the field :func:`..resources.alternatives.new_document`
  writes; a date already there is confirmed (or corrected). A document without
  a date is refused;
* **«Che epoca rappresenta?»** is another question, and its answer goes to the
  MODELS (``EpochNode ──has_representation_model──▶ RM``), NEVER to the
  document as its date (D.09: a reconstruction made in 2026 that represents the
  II A.D.); the document gets no epoch from here;
* the **role in the space**: a GIS file is always an RMDoc (not asked); a 3D
  model is an RM (in the epoch it represents) or an RMDoc; a mesh brought in
  with a tileset can be its SOURCE (``source``: the tileset's master,
  :func:`..resources.graph_compose.declare_tileset_master`, not drawn);
* the **licence** proposed by the document (``has_license`` on the document,
  inherited by what it holds — «solo studio» too).

A file already in the graph (an RM whose resource has the same locator, e.g. a
tileset that was an RM without a document) is NOT duplicated: its model is
published by the document (``has_representation_model``) and, when an epoch is
given, kept in it.

→ ``{document_id, document_name, document_born, date, items: [{path, kind,
role, resource_id, model_id, reused}], gis: {…} | None, warnings}``.
"""
from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Optional

GIS_EXT = {".tif", ".tiff", ".jpg", ".jpeg", ".png", ".shp", ".gpkg", ".geojson", ".json", ".dxf"}
MODEL_EXT = {".obj", ".glb", ".gltf", ".ply", ".fbx", ".stl", ".las", ".laz", ".e57", ".blend"}
TILESET_EXT = {".3tz"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}
TROPY_EXT = {".tpy", ".jsonld"}
ROLES = ("rm", "rmdoc", "source")


def kind_of(path: str, *, georeferenced: Optional[bool] = None) -> str:
    """What a file is, by its name: ``tileset`` (a .3tz or a tileset.json),
    ``model``, ``dxf``, ``vector``, ``raster`` (a picture with a world file or a
    GeoTIFF: ``georeferenced`` says it, the caller read it), ``image``, ``tropy``,
    ``graph`` (an em.json / GraphML: not this door's), ``other``."""
    p = str(path).lower().rstrip("/")
    base = os.path.basename(p)
    ext = os.path.splitext(base)[1]
    if base.endswith(".em.json") or ext == ".graphml":
        return "graph"
    if ext in TILESET_EXT or base == "tileset.json":
        return "tileset"
    if ext in TROPY_EXT:
        return "tropy"
    if ext in MODEL_EXT:
        return "model"
    if ext == ".dxf":
        return "dxf"
    if ext in (".shp", ".gpkg", ".geojson"):
        return "vector"
    if ext in IMAGE_EXT:
        return "raster" if georeferenced else "image"
    return "other"


def _node(graph, nid):
    return graph.find_node_by_id(nid)


def _data(n) -> Dict[str, Any]:
    d = getattr(n, "data", None)
    if not isinstance(d, dict):
        d = {}
        n.data = d
    return d


def _norm(u: str) -> str:
    """a locator as compared: normalised, lower case, without its leading ``../`` / ``./``"""
    v = os.path.normpath(str(u or "").strip()).replace("\\", "/").lower()
    while v.startswith("../") or v.startswith("./"):
        v = v[3:] if v.startswith("../") else v[2:]
    return "" if v in (".", "") else v


def model_of_locator(graph, url: str) -> Optional[Dict[str, str]]:
    """An RM / RMDoc whose resource (or own ``url`` / ``tileset_path``) has this locator."""
    want = _norm(url)
    if not want:
        return None
    for n in graph.nodes:
        if getattr(n, "node_type", "") not in ("representation_model", "representation_model_doc"):
            continue
        d = _data(n)
        res = [e.edge_target for e in graph.edges if e.edge_source == n.node_id and e.edge_type == "has_linked_resource"]
        urls = {_norm(d.get("url") or ""), _norm(d.get("tileset_path") or "")}
        urls |= {_norm(_data(_node(graph, r)).get("url") or "") for r in res if _node(graph, r) is not None}
        if want in urls:
            return {"model": n.node_id, "resource": res[0] if res else ""}
    return None


def resource_of_locator(graph, url: str) -> Optional[str]:
    want = _norm(url)
    for n in graph.nodes:
        if getattr(n, "node_type", "") == "resource" and _norm(_data(n).get("url") or "") == want:
            return n.node_id
    return None


def _edge(graph, s: str, t: str, et: str) -> None:
    if not any(e.edge_source == s and e.edge_target == t and e.edge_type == et for e in graph.edges):
        graph.add_edge(f"{s}_{et}_{t}", s, t, et)


def bring_in(graph, files: Iterable[Mapping[str, Any]], *, document_id: Optional[str] = None,
             title: str = "", name: Optional[str] = None, date: Any = None, epoch_id: Optional[str] = None,
             license: Optional[str] = None, author_id: Optional[str] = None,
             gis: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Files into a document (see the module). ``files``: ``{path, url?, name?,
    kind?, role?, packaging?, checksum?, size_bytes?, media_type?, name_only?}``
    — ``url`` the locator written (default ``path``), ``role`` one of
    :data:`ROLES` for a model or a tileset (default ``rm``); the rest is what a
    tileset's preview read (MICRO-F p.2: a tileset dropped passes by the door). ``gis``:
    the extra arguments of :func:`..gis.document.add_gis_document` (crs, shift,
    urls) for the GIS files among them."""
    from .document_names import next_document_name
    from .gis.document import add_gis_document, set_license
    from .nodes.representation_node import RepresentationModelDocNode, RepresentationModelNode
    from .resources.alternatives import new_document
    from .resources.files import add_resource

    files = [dict(f) for f in files]
    if not files:
        raise ValueError("no file to bring in")
    if date is None or str(date).strip() == "":
        raise ValueError("the document's date is wanted: «Quando è stato fatto questo documento?»")
    if epoch_id and getattr(_node(graph, epoch_id), "node_type", "") != "EpochNode":
        raise ValueError(f"{epoch_id!r} is not an epoch of this graph")
    warnings: List[str] = []
    born = False
    if document_id:
        doc = _node(graph, document_id)
        if doc is None or getattr(doc, "node_type", "") != "document":
            raise ValueError(f"{document_id!r} is not a document of this graph")
        d = _data(doc)
        if str(d.get("absolute_time_start") or "") != str(date):
            if d.get("absolute_time_start"):
                warnings.append(f"data del documento corretta: {d.get('absolute_time_start')} → {date}")
            d["absolute_time_start"] = date
    else:
        dname = str(name or "").strip() or next_document_name(graph)
        document_id = new_document(graph, dname, description=str(title or ""), date=date, author_id=author_id)
        doc = _node(graph, document_id)
        born = True
    if license:
        set_license(graph, document_id, license)

    gis_files = [f for f in files if (f.get("kind") or kind_of(f["path"])) in ("raster", "vector", "dxf")]
    other = [f for f in files if f not in gis_files]
    items: List[Dict[str, Any]] = []
    gis_out = None
    if gis_files:
        g = dict(gis or {})
        gis_out = add_gis_document(graph, [f["path"] for f in gis_files], document_id=document_id,
                                   crs=g.get("crs"), shift=g.get("shift"), urls=g.get("urls"))
        for s in gis_out.get("sheets") or []:
            items.append({"path": s.get("path"), "kind": "gis", "role": "rmdoc", "resource_id": s.get("id"),
                          "model_id": gis_out.get("rmdoc_id"), "reused": False})
        warnings += list(gis_out.get("warnings") or [])

    tilesets: List[str] = []
    sources: List[str] = []
    for f in other:
        path = str(f["path"])
        url = str(f.get("url") or path)
        kind = str(f.get("kind") or kind_of(path))
        role = str(f.get("role") or "rm")
        if role not in ROLES:
            raise ValueError(f"{role!r} is not a role of a model ({', '.join(ROLES)})")
        name = str(f.get("name") or os.path.splitext(os.path.basename(path.rstrip("/")))[0])
        if kind in ("image", "other"):
            # a picture without a frame: a file of the document, no place in the space
            rid = resource_of_locator(graph, url) or add_resource(graph, name=name, files=[{"path": url}]).node_id
            _edge(graph, document_id, rid, "has_linked_resource")
            items.append({"path": path, "kind": kind, "role": "file", "resource_id": rid, "model_id": None, "reused": False})
            continue
        hit = model_of_locator(graph, url)
        if hit and role != "source":
            mid, rid = hit["model"], hit["resource"]
            mt = getattr(_node(graph, mid), "node_type", "")
            et = "has_representation_model_doc" if mt == "representation_model_doc" else "has_representation_model"
            _edge(graph, document_id, mid, et)
            if epoch_id and et == "has_representation_model":
                _edge(graph, epoch_id, mid, "has_representation_model")
            items.append({"path": path, "kind": kind, "role": "rmdoc" if mt == "representation_model_doc" else "rm",
                          "resource_id": rid, "model_id": mid, "reused": True})
            if kind == "tileset" and rid:
                tilesets.append(rid)
            continue
        rid = resource_of_locator(graph, url)
        reused = bool(rid)
        if not rid:
            # MICRO-F p.2 · what the tileset's preview knew passes with the file:
            # its packaging (a .3tz / .zip an archive, a folder's tileset.json a
            # directory), its digest (a resource with one is resident), its size,
            # and that only its NAME is known (a drop from the system in a browser)
            low = url.lower()
            packaging = f.get("packaging") or (
                "archive" if low.endswith(".3tz") or (kind == "tileset" and low.endswith(".zip")) else None)
            spec = {"path": url}
            for k in ("checksum", "size_bytes", "media_type"):
                if f.get(k):
                    spec[k] = f[k]
            extra: Dict[str, Any] = {}
            if f.get("name_only"):
                extra["locator_note"] = "name only: the file was dropped, its path is not known"
            elif f.get("checksum") and packaging == "directory":
                extra["checksum_of"] = "entry-point"
            rid = add_resource(graph, name=name, kind="3d_model", tier="master", files=[spec],
                               packaging=packaging, residency="resident" if f.get("checksum") else None,
                               data=extra).node_id
        if role == "source":
            _edge(graph, document_id, rid, "has_linked_resource")
            sources.append(rid)
            items.append({"path": path, "kind": kind, "role": "source", "resource_id": rid, "model_id": None, "reused": reused})
            continue
        mid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"door:{document_id}:{rid}"))
        if role == "rmdoc":
            graph.add_node(RepresentationModelDocNode(mid, name=name, type="generic", description=""))
            _edge(graph, document_id, mid, "has_representation_model_doc")
        else:
            graph.add_node(RepresentationModelNode(mid, name=name))
            if kind == "tileset":
                _data(_node(graph, mid)).update({"is_tileset": True, "tileset_path": url, "url": url})
            _edge(graph, document_id, mid, "has_representation_model")
            if epoch_id:
                _edge(graph, epoch_id, mid, "has_representation_model")
        _edge(graph, mid, rid, "has_linked_resource")
        if kind == "tileset":
            tilesets.append(rid)
        items.append({"path": path, "kind": kind, "role": role, "resource_id": rid, "model_id": mid, "reused": reused})
    # a mesh brought in as SOURCE of the tileset(s) brought in with it: their master
    if sources and tilesets:
        from .resources.graph_compose import declare_tileset_master
        for t in tilesets:
            try:
                declare_tileset_master(graph, t, sources)
            except ValueError as exc:
                warnings.append(str(exc))
    elif sources:
        warnings.append("una sorgente senza tileset: resta un file del documento")
    return {"document_id": document_id, "document_name": str(getattr(doc, "name", "") or ""),
            "document_born": born, "date": date, "epoch_id": epoch_id, "items": items,
            "gis": gis_out, "warnings": warnings}


def tropy_plan(items: Iterable[Mapping[str, Any]], graph=None) -> List[Dict[str, Any]]:
    """Tropy through the same door, another form: one row per ITEM → one
    document, its photos its files (MICRO-B), date and licence read from the
    item; ``missing_date`` marks the rows to fill; ``merge_with`` an existing
    document of the same name (``D.nn``). Nothing is written: the page shows the
    table and confirms it in one block."""
    docs = {}
    if graph is not None:
        for n in graph.nodes:
            if getattr(n, "node_type", "") == "document":
                docs[str(getattr(n, "name", "") or "").strip()] = n.node_id
    out = []
    for it in items:
        title = str(it.get("title") or it.get("name") or "").strip()
        date = str(it.get("date") or "").strip()
        out.append({"title": title, "date": date, "license": str(it.get("license") or it.get("rights") or ""),
                    "photos": list(it.get("photos") or []), "missing_date": not date,
                    "merge_with": docs.get(title) or docs.get(str(it.get("identifier") or "").strip())})
    return out


__all__ = ["kind_of", "bring_in", "model_of_locator", "resource_of_locator", "tropy_plan", "ROLES"]
