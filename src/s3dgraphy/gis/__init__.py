"""GIS in the em.json: the site, its footprint, a GIS layer as a resource.

MICRO lab sito Sarmizegetusa (30 Oct 2026), on the decisions of
``landscape-graph-semantica`` (D-LG4/D-LG5) and the proposal «Il GIS dentro
l'em.json» (Part 5, 25 Oct 2026). The grid of ingestion is the 3D one: a file
becomes a RESOURCE (stamped by the DTC), the resource has its FRAME (CRS +
shift, ``data.frame``), a SEMANTIC NODE represents it. A GIS format enters only
when it has a node to hang from.

* :mod:`.crs` — reading a ``.prj`` / ``.qpj``, and the rule «same grid,
  different code» (EPSG:31700, deprecated ↔ EPSG:3844);
* :mod:`.shapefile` — a shapefile read without GDAL (points, lines, polygons;
  the dbf attributes);
* :mod:`.layer` — the layer as a ``ResourceNode`` of url_type ``gis_layer``;
* :mod:`.site` — the site (a ``LocationNodeGroup`` with ``place_type: site``),
  its footprint (a ``PropertyNode`` of qualia ``footprint``, WKT with its CRS)
  and the footprint read from the proxies of its units.
"""

from .crs import same_grid, crs_of_prj, crs_of_shapefile, SAME_GRID
from .shapefile import read_shapefile, ShapefileError
from .layer import add_gis_layer, gis_layers, GIS_FORMATS
from .site import (add_site, sites, site_of, set_footprint, footprint_of,
                   footprint_from_glbs, plan_hull, PLACE_TYPES)

__all__ = [
    "same_grid", "crs_of_prj", "crs_of_shapefile", "SAME_GRID",
    "read_shapefile", "ShapefileError",
    "add_gis_layer", "gis_layers", "GIS_FORMATS",
    "add_site", "sites", "site_of", "set_footprint", "footprint_of",
    "footprint_from_glbs", "plan_hull", "PLACE_TYPES",
]
