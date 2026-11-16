"""GIS data as DOCUMENTS (MICRO-D-GIS-DOCUMENTI, E.D. 15 Nov 2026).

A cartographic source — a cadastre, a historical plan, an orthophoto, contour
lines, a CAD plan — is a **document** (``D.nn``). Its sheets are FILES OF ONE
RESOURCE under that document, the scheme of the photographs of
MICRO-B-DOCUMENTI-MEDIA::

    D.nn ──has_linked_resource──▶ ResourceNode (url_type gis_layer, file_set,
                                   data.gis_document: true)
                                     └─has_file──▶ ResourceFileNode per sheet
                                                   (data.gis_format, crs, bbox,
                                                    raster | features, frame)
    D.nn ──has_representation_model_doc──▶ RMDoc ──has_linked_resource──▶ the set

* In the space the document has an **RMDoc**, never an RM: it does not
  represent the place in an epoch. A reconstruction laid over it is an RM of
  its own, which uses the RMDoc as its base.
* The document's DATE (a cadastre of 1835) is a date — ``data.
  absolute_time_start`` of the document — and **never an epoch**: nothing here
  creates nor links an epoch.
* Each sheet DECLARES its frame (``data.frame``: the CRS of the file and the
  shift its numbers are written with — zero for a file in grid coordinates,
  the shift asked for a DXF). The CONVERSION to the graph's CRS is not
  computed here (s3Dgraphy orders, it does not compute for one tool): the
  bridge of EMStudio reprojects with PROJ and says «convertito da EPSG:3004 a
  EPSG:32633». The rule «same grid, different code» (31700 ↔ 3844) stays:
  such a sheet's frame is the graph's.
* The LICENCE sits on the document (``has_license``); the sheets inherit it
  through the resolver of provenance (``set`` → ``publisher``). The value
  «uso di studio, non pubblicabile» is :data:`..rights.STUDY_ONLY_LICENSE`.

:func:`add_gis_document` is the one door; :func:`gis_documents` reads them back.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from ..geometry.frame import make_frame, normalise_crs
from .crs import same_grid
from .layer import _MEDIA, _MEDIA_ONE, _graph_crs, _sha256, bbox_wgs84, format_of, inspect_layer
from .shapefile import companions
from ..document_names import next_document_name  # noqa: F401 — the one rule (MICRO-F p.3)

#: the document's type in ``em_document_types.json`` (2.2): a cartographic source
DOCUMENT_TYPE = "spatial_documentation"
DOCUMENT_SUBTYPE = "cartography"
_IMG_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def _nodes(graph):
    return list(getattr(graph, "nodes", []) or [])


def _node(graph, nid):
    return graph.find_node_by_id(nid) if nid else None


def gis_set_of(graph, document_id: str) -> Optional[str]:
    """The GIS set a document links (``data.gis_document``), or None."""
    for e in graph.edges:
        if e.edge_type == "has_linked_resource" and e.edge_source == document_id:
            r = _node(graph, e.edge_target)
            d = getattr(r, "data", None) or {}
            if getattr(r, "node_type", "") == "resource" and d.get("gis_document"):
                return e.edge_target
    return None


def _rmdoc_of(graph, document_id: str) -> Optional[str]:
    for e in graph.edges:
        if e.edge_type == "has_representation_model_doc" and e.edge_source == document_id:
            return e.edge_target
    return None


def _sheet_files(path: str, fmt: str, url: str) -> List[Dict[str, Any]]:
    """The bytes of one sheet: the entry file and its companions (a shapefile's
    .dbf / .shx / .prj, a picture's world file and .prj)."""
    url_dir = os.path.dirname(url)
    if fmt == "shapefile":
        paths = companions(path)
    elif fmt == "worldfile_image":
        from .worldfile import world_file_of
        stem = os.path.splitext(path)[0]
        paths = [path] + [p for p in (world_file_of(path), stem + ".prj") if p and os.path.exists(p)]
    else:
        paths = [path]
    out = []
    for p in paths:
        leaf = os.path.basename(p)
        ext = os.path.splitext(leaf)[1].lower()
        spec = {"path": leaf, "url": (url_dir + "/" + leaf) if url_dir else leaf,
                "checksum": _sha256(p), "size_bytes": os.path.getsize(p)}
        if p == path:
            spec["url"] = url
        media = _MEDIA.get(ext) or _IMG_MEDIA.get(ext) or (_MEDIA_ONE.get(fmt) if p == path else None)
        if media:
            spec["media_type"] = media
        out.append(spec)
    return out


def _pick(value: Union[None, str, Sequence[Any], Mapping[str, Any]], path: str):
    """A per-file option: one value for all, or a mapping by path / basename."""
    if isinstance(value, Mapping):
        return value.get(path, value.get(os.path.basename(path)))
    return value


def set_license(graph, node_id: str, license_type: str, *, name: Optional[str] = None,
                url: str = "") -> str:
    """``node ──has_license──▶ LicenseNode`` of ``license_type`` (a licence node
    of that type already in the graph is reused); the node's other licences
    are taken off (one licence a node). → the licence's id."""
    from ..nodes.license_node import LicenseNode
    lic = next((n for n in _nodes(graph) if getattr(n, "node_type", "") == "license"
                and (getattr(n, "data", None) or {}).get("license_type") == license_type), None)
    if lic is None:
        from ..rights import LICENSE_LABELS
        lid = str(uuid.uuid5(uuid.NAMESPACE_URL, "license:" + license_type))
        lic = _node(graph, lid) or LicenseNode(lid, name=name or LICENSE_LABELS.get(license_type, license_type),
                                               license_type=license_type, url=url)
        if _node(graph, lid) is None:
            graph.add_node(lic)
    for e in list(graph.edges):
        if e.edge_type == "has_license" and e.edge_source == node_id and e.edge_target != lic.node_id:
            graph.remove_edge(e.edge_id)
    eid = f"{node_id}_has_license_{lic.node_id}"
    if graph.find_edge_by_id(eid) is None:
        graph.add_edge(eid, node_id, lic.node_id, "has_license")
    return lic.node_id


def add_gis_document(graph, paths: Iterable[str], *, document_id: Optional[str] = None,
                     name: Optional[str] = None, description: str = "", date: Any = None,
                     license: Optional[str] = None, crs: Union[None, str, Mapping[str, str]] = None,
                     shift: Union[None, Sequence[float], Mapping[str, Sequence[float]]] = None,
                     urls: Optional[Mapping[str, str]] = None,
                     author_id: Optional[str] = None) -> Dict[str, Any]:
    """Bring GIS files into the graph as the SHEETS of one document.

    ``paths`` — the files (a GeoTIFF, a JPEG / PNG with a world file, a
    shapefile, a GeoPackage, a GeoJSON, a DXF): several in one go are sheets
    of the same document. ``document_id`` — an existing document (its set
    gets the new sheets); else a NEW document named ``name`` (default the
    study's next ``D.nn``), with ``description`` and ``date``
    (``data.absolute_time_start``: a date, never an epoch). ``license`` — a
    licence type written on the DOCUMENT (the sheets inherit it), e.g.
    :data:`..rights.STUDY_ONLY_LICENSE`. ``crs`` / ``shift`` — the CRS and the
    shift of a file that declares none (a DXF; one value for all or a mapping
    by path): its frame. ``urls`` — the locator written for each path
    (default its basename).

    → ``{document_id, document_name, document_born, set_id, rmdoc_id,
    license_id, sheets: [{id, path, name, gis_format, crs, frame, same_grid,
    convert: {from, to} | None}], warnings}``. ``convert`` says what the
    viewer must do («convertito da … a …»): nothing is converted here."""
    from ..nodes.representation_node import RepresentationModelDocNode
    from ..resources.files import add_resource, _write_file

    paths = [str(p) for p in paths]
    if not paths:
        raise ValueError("no file to bring in")
    gcrs = _graph_crs(graph)
    warnings: List[str] = []
    born = False
    if document_id:
        doc = _node(graph, document_id)
        if doc is None or getattr(doc, "node_type", "") != "document":
            raise ValueError(f"{document_id!r} is not a document of this graph")
    else:
        from ..resources.alternatives import new_document
        dname = str(name or "").strip() or next_document_name(graph)
        document_id = new_document(graph, dname, description=description or "", date=date,
                                   author_id=author_id)
        doc = _node(graph, document_id)
        doc.data["document_type"] = DOCUMENT_TYPE
        doc.data["document_subtype"] = DOCUMENT_SUBTYPE
        born = True
    set_id = gis_set_of(graph, document_id)
    if set_id is None:
        set_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "gis_document:" + document_id))
        add_resource(graph, name=f"{doc.name} · GIS", kind="gis_layer", packaging="file_set",
                     resource_id=set_id, description=description or "",
                     data={"gis_document": True})
        graph.add_edge(f"{document_id}_has_linked_resource_{set_id}", document_id, set_id,
                       "has_linked_resource")
    rmdoc = _rmdoc_of(graph, document_id)
    if rmdoc is None:
        rmdoc = str(uuid.uuid5(uuid.NAMESPACE_URL, "gis_rmdoc:" + document_id))
        graph.add_node(RepresentationModelDocNode(rmdoc, name=f"{doc.name} (RMDoc)", type="generic",
                                                  description="the document laid in the space: a base, never an epoch"))
        graph.add_edge(f"{document_id}_has_representation_model_doc_{rmdoc}", document_id, rmdoc,
                       "has_representation_model_doc")
        graph.add_edge(f"{rmdoc}_has_linked_resource_{set_id}", rmdoc, set_id, "has_linked_resource")
    sheets = []
    for p in paths:
        fmt = format_of(p)
        if fmt is None:
            raise ValueError(f"{os.path.basename(p)}: not a GIS file read here "
                             "(tif, jpg/png with a world file, shp, gpkg, geojson, dxf)")
        ins = inspect_layer(p)
        declared = normalise_crs(_pick(crs, p)) or ins["crs"]
        sh = _pick(shift, p) or [0.0, 0.0, 0.0]
        sg = bool(declared and gcrs and same_grid(declared, gcrs))
        frame_crs = gcrs if sg else declared
        frame = make_frame(frame_crs, sh, source="manual" if fmt == "dxf" else "file",
                           note=(f"declared {declared}; same grid as {gcrs}" if sg and declared != gcrs else "")) \
            if frame_crs else None
        convert = {"from": declared, "to": gcrs} if declared and gcrs and not sg else None
        if not declared:
            warnings.append(f"{os.path.basename(p)} declares no CRS: say which before it can be placed")
        url = (urls or {}).get(p) or os.path.basename(p)
        specs = _sheet_files(p, fmt, url)
        entry = specs[0]
        node = _write_file(graph, set_id, {**entry, "role": "member"}, "member")
        d = node.data
        d.update({"gis_format": fmt, "crs": declared, "bbox": ins["bbox"]})
        bw = bbox_wgs84(ins["bbox"], declared) if declared else None
        if bw:
            d["bbox_wgs84"] = bw
        for k in ("geometry_type", "feature_count", "feature_key", "z_field", "z_range", "layer",
                  "dxf_layers"):
            if ins.get(k) not in (None, "", []):
                d[k] = ins[k]
        if ins.get("raster"):
            d["raster"] = {k: v for k, v in ins["raster"].items() if v is not None}
        if frame:
            d["frame"] = frame
        if len(specs) > 1:
            d["companions"] = specs[1:]
        sheets.append({"id": node.node_id, "path": p, "name": node.name, "gis_format": fmt,
                       "crs": declared, "frame": frame, "same_grid": sg, "convert": convert})
    from ..resources.files import refresh_members_digest
    refresh_members_digest(graph, set_id)
    lic_id = set_license(graph, document_id, license) if license else None
    return {"document_id": document_id, "document_name": doc.name, "document_born": born,
            "set_id": set_id, "rmdoc_id": rmdoc, "license_id": lic_id, "sheets": sheets,
            "warnings": warnings}


def gis_documents(graph) -> List[Dict[str, Any]]:
    """The GIS documents of a graph: ``[{document_id, name, set_id, rmdoc_id,
    sheets: [ids]}]``."""
    out = []
    for n in _nodes(graph):
        if getattr(n, "node_type", "") != "document":
            continue
        sid = gis_set_of(graph, n.node_id)
        if not sid:
            continue
        files = [e.edge_target for e in graph.edges if e.edge_type == "has_file" and e.edge_source == sid]
        out.append({"document_id": n.node_id, "name": n.name, "set_id": sid,
                    "rmdoc_id": _rmdoc_of(graph, n.node_id), "sheets": files})
    return out
