"""The footprints of a pyArchInit excavation: places and cuts, from its layers.

NIGHT «impronte di saggi e tagli» (decided by E.D. 2026-11-11). PyArchInit draws
its excavation in GIS layers of the same database (SpatiaLite or PostGIS); the
importer read the TABLES and left the drawings out — EM Tools turned them into
Blender meshes and nothing stayed in the em.json. Now, after the rows, the
layers the mapping declares (``footprint_layers``) are read:

* the SITE (``pyarchinit_siti_polygonal``) → the site place (level ``sito``);
* the PLACES (``pyarchinit_sondaggi`` → the saggio, ``pyarchinit_ripartizioni_
  spaziali`` → the area / settore its ``tip_rip`` names) → the
  ``LocationNodeGroup`` the rows made (``loc::<column>::study::<value>``);
* the UNITS (``pyunitastratigrafiche``) → ONLY the negative ones
  (``NegativeStratigraphicUnit``): a positive unit's geometry is the proxy, and
  its polygons are COUNTED, not written (:mod:`s3dgraphy.gis.footprint`).

Each layer becomes ONE ``gis_layer`` resource (``gis_format`` spatialite or
postgis, ``data.layer`` the table) hatted by a DocumentNode — the plan drawn in
pyArchInit — and each footprint's extractor is ``extracted_from`` that document
with ``data.layer``/``feature_key``/``feature`` naming its feature. The
resource's locator is ``layer_url`` when the caller has one (the address in a
node's bucket), else the database's local path (a PostGIS DSN without its
password).

Measured on pyArchInit's demo database (12 Nov 2026): the geometry is
SpatiaLite's BLOB, not WKB (:mod:`s3dgraphy.gis.spatialite`); the CRS is the
layer's ``geometry_columns.srid``.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..gis.footprint import footprint_verdict, write_footprint
from ..gis.spatialite import read_spatialite_geometry

_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://w3id.org/em/pyarchinit/footprint-layer")


def _norm(v: Any) -> str:
    return str(v if v is not None else "").strip()


class FootprintReader:
    """Reads the declared layers through an OPEN connection of the importer."""

    def __init__(self, importer, conn, config: Dict[str, Any], *,
                 layer_url: Optional[str] = None, author: Optional[str] = None):
        self.imp = importer
        self.graph = importer.graph
        self.conn = conn
        self.cfg = config or {}
        self.layer_url = layer_url
        self.author = author
        self.dialect = getattr(importer, "_dialect", "sqlite")
        self.report: Dict[str, Any] = {
            "places_with_footprint": 0, "site_with_footprint": 0,
            "cuts_with_footprint": 0, "positive_units_excluded": 0,
            "unmatched_features": 0, "layers_registered": 0,
            "simplified": 0, "layers": {}, "warnings": []}
        self._docs: Dict[str, str] = {}

    # ── the database ────────────────────────────────────────────────────
    def _q(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        cur = self.conn.cursor()
        if self.dialect == "postgres":
            sql = sql.replace("?", "%s")
        cur.execute(sql, params)
        return cur.fetchall()

    def _has_table(self, table: str) -> bool:
        try:
            if self.dialect == "postgres":
                return bool(self._q("SELECT 1 FROM information_schema.tables "
                                    "WHERE table_name = ?", (table,)))
            return bool(self._q("SELECT 1 FROM sqlite_master WHERE name = ? "
                                "AND type IN ('table','view')", (table,)))
        except Exception:  # noqa: BLE001
            return False

    def _srid(self, table: str, column: str) -> Optional[int]:
        try:
            rows = self._q("SELECT srid FROM geometry_columns WHERE "
                           "lower(f_table_name) = lower(?) AND "
                           "lower(f_geometry_column) = lower(?)", (table, column))
        except Exception:  # noqa: BLE001
            return None
        return int(rows[0][0]) if rows and rows[0][0] not in (None, -1, 0) else None

    def _features(self, table: str, columns: List[str], geom: str = "the_geom"):
        for c in columns + [table, geom]:
            if not self.imp._is_safe_identifier(c):
                raise ValueError(f"unsafe identifier {c!r} in footprint_layers")
        g = f"ST_AsBinary({geom})" if self.dialect == "postgres" else geom
        sql = f"SELECT {', '.join(columns)}, {g} FROM {table} WHERE {geom} IS NOT NULL"
        for row in self._q(sql):
            yield row[:-1], row[-1]

    # ── the layer as a resource ─────────────────────────────────────────
    def _layer(self, table: str, crs: Optional[str], key: str, count: int,
               gtype: str, bbox: Optional[List[float]]) -> str:
        """The gis_layer resource of ``table`` and the document that hats
        it; returns the DOCUMENT's id (what the extractors cite)."""
        if table in self._docs:
            return self._docs[table]
        from ..nodes.document_node import DocumentNode
        from ..resources.files import add_resource
        from ..importer.base_importer import redact_dsn
        local = self.dialect == "sqlite"
        db = self.imp.filepath
        locator = self.layer_url or (os.path.abspath(db) if local else redact_dsn(db))
        rid = str(uuid.uuid5(_NS, f"{locator}#{table}"))
        files = []
        if local and os.path.isfile(db):
            h = hashlib.sha256()
            with open(db, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            files = [{"path": os.path.basename(db), "url": locator,
                      "checksum": "sha256:" + h.hexdigest(),
                      "size_bytes": os.path.getsize(db), "role": "entry_point",
                      "media_type": "application/vnd.sqlite3"}]
        if self.graph.find_node_by_id(rid) is None:
            data = {"gis_format": "spatialite" if local else "postgis", "layer": table,
                    "crs": crs, "feature_key": key, "feature_count": count,
                    "geometry_type": gtype, "source": "pyarchinit"}
            if bbox:
                data["bbox"] = bbox
            if not files:
                data["locator"] = locator
            add_resource(self.graph, name=f"pyArchInit · {table}", kind="gis_layer",
                         files=files, packaging="file", resource_id=rid,
                         description=f"pyArchInit layer {table}", data=data)
            self.report["layers_registered"] += 1
        did = str(uuid.uuid5(_NS, f"{rid}|document"))
        if self.graph.find_node_by_id(did) is None:
            self.graph.add_node(DocumentNode(
                did, f"pyArchInit plan · {table}",
                description=f"The plan drawn in pyArchInit's layer {table}"))
        eid = f"{did}__has_linked_resource__{rid}"
        if self.graph.find_edge_by_id(eid) is None:
            self.graph.add_edge(eid, did, rid, "has_linked_resource")
        self._docs[table] = did
        return did

    # ── one layer ───────────────────────────────────────────────────────
    def _read_layer(self, spec: Dict[str, Any], resolve) -> None:
        table = spec.get("table")
        if not table or not self._has_table(table):
            return
        site_col = spec.get("site_column")
        key_col = spec.get("key_column")
        extra = [c for c in (spec.get("area_column"), spec.get("type_column")) if c]
        cols = [c for c in (site_col, key_col) if c] + extra
        srid = self._srid(table, spec.get("geometry_column", "the_geom"))
        stats = {"features": 0, "written": 0, "excluded_positive": 0, "unmatched": 0}
        groups: Dict[str, Dict[str, Any]] = {}
        sites = self.imp._footprint_sites()
        for vals, blob in self._features(table, cols, spec.get("geometry_column", "the_geom")):
            row = dict(zip(cols, vals))
            if site_col and sites and _norm(row.get(site_col)) not in sites:
                continue
            stats["features"] += 1
            try:
                g = read_spatialite_geometry(blob)
            except Exception as e:  # noqa: BLE001
                self.report["warnings"].append(f"{table}: a geometry not read ({e})")
                continue
            polys = (g or {}).get("polygons")
            if not polys:
                continue
            target = resolve(row)
            if target is None:
                stats["unmatched"] += 1
                continue
            v = footprint_verdict(target)
            if not v["ok"]:
                stats["excluded_positive"] += 1
                continue
            slot = groups.setdefault(target.node_id, {"node": target, "polygons": [],
                                                      "feature": _norm(row.get(key_col)),
                                                      "srid": srid or g.get("srid")})
            slot["polygons"] += polys
        crs = f"EPSG:{srid}" if srid else None
        all_pts = [p for s in groups.values() for poly in s["polygons"] for r in poly for p in r]
        bbox = ([min(p[0] for p in all_pts), min(p[1] for p in all_pts),
                 max(p[0] for p in all_pts), max(p[1] for p in all_pts)] if all_pts else None)
        if groups:
            doc = self._layer(table, crs, key_col, stats["features"],
                              spec.get("geometry_type", "Polygon"), bbox)
            for nid, slot in groups.items():
                c = crs or (f"EPSG:{slot['srid']}" if slot["srid"] else None)
                if not c:
                    self.report["warnings"].append(
                        f"{table}: no CRS for {slot['node'].name} — not written")
                    continue
                out = write_footprint(self.graph, slot["node"], slot["polygons"], c,
                                      sources=[doc], layer=table, feature_key=key_col,
                                      feature=slot["feature"], method="gis_analysis",
                                      extractor_name=f"D.footprint.{table}",
                                      note=f"Read from pyArchInit's layer {table}",
                                      author=self.author)
                stats["written"] += 1
                if out["simplified"]:
                    self.report["simplified"] += 1
                if out["owner"] == "cut":
                    self.report["cuts_with_footprint"] += 1
                elif _norm(getattr(slot["node"], "attributes", {}).get("level")) == "sito":
                    self.report["site_with_footprint"] += 1
                else:
                    self.report["places_with_footprint"] += 1
        self.report["positive_units_excluded"] += stats["excluded_positive"]
        self.report["unmatched_features"] += stats["unmatched"]
        self.report["layers"][table] = stats

    # ── the four kinds of layer ─────────────────────────────────────────
    def run(self) -> Dict[str, Any]:
        cfg = self.cfg
        site_spec = cfg.get("site")
        if site_spec:
            def site_target(row):
                from ..gis.site import add_site
                name = _norm(row.get(site_spec.get("site_column")))
                return add_site(self.graph, name) if name else None
            self._read_layer({**site_spec, "key_column": site_spec.get("site_column"),
                              "site_column": site_spec.get("site_column")}, site_target)
        for spec in cfg.get("places") or []:
            def place_target(row, spec=spec):
                key = _norm(row.get(spec.get("key_column")))
                col = spec.get("location_column")
                if spec.get("type_column"):
                    t = _norm(row.get(spec["type_column"])).lower()
                    col = (spec.get("location_column_by_type") or {}).get(t)
                if not col or not key:
                    return None
                return self.graph.find_node_by_id(f"loc::{col}::study::{key}")
            self._read_layer(spec, place_target)
        units = cfg.get("units")
        if units:
            def unit_target(row):
                k = (_norm(row.get(units.get("site_column"))),
                     _norm(row.get(units.get("area_column"))),
                     _norm(row.get(units.get("key_column"))))
                nid = self.imp._unit_index.get(k)
                return self.graph.find_node_by_id(nid) if nid else None
            self._read_layer(units, unit_target)
        self._link_places_to_site()
        return self.report

    def _link_places_to_site(self) -> None:
        """A saggio is in its site (nodes 1.6.29): each study place made by the
        rows ``is_in_location`` the site, when the site has a footprint here
        and is the only one."""
        from ..gis.site import sites
        s = [n for n in sites(self.graph)]
        if len(s) != 1:
            return
        site = s[0]
        for n in list(self.graph.nodes):
            if (getattr(n, "node_type", None) == "LocationNodeGroup"
                    and str(n.node_id).startswith("loc::")
                    and getattr(n, "kind", None) == "study"):
                eid = f"{n.node_id}_is_in_location_{site.node_id}"
                if self.graph.find_edge_by_id(eid) is None:
                    self.graph.add_edge(eid, n.node_id, site.node_id, "is_in_location")
