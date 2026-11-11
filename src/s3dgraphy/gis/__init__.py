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
* :mod:`.geojson`, :mod:`.geopackage` (+ :mod:`.wkb`), :mod:`.geotiff` — the
  other three base formats, without GDAL (MICRO-GIS-BASE, 6 Nov 2026): the CRS
  read from the file, the bbox in it and in WGS 84;
* :mod:`.contours` — contour lines of a DEM (marching squares);
* :mod:`.landscape` — the ground of the landscape (``LandscapeSurfaceNode``)
  and the contours as a derived, stamped layer;
* :mod:`.layer` — the layer as a ``ResourceNode`` of url_type ``gis_layer``;
* :mod:`.site` — the site (a ``LocationNodeGroup`` with ``place_type: site``),
  its footprint (a ``PropertyNode`` of qualia ``footprint``, WKT with its CRS)
  and the footprint read from the proxies of its units;
* :mod:`.footprint` — WHO may carry a footprint (the datamodel's
  ``applies_to``: the site, the operational places — area, saggio — and the
  CUTS, USN; never a positive unit, whose geometry is the proxy), the writer
  every owner shares, the simplification above 500 vertices;
* :mod:`.spatialite` — a SpatiaLite geometry blob (pyArchInit's layers) read
  without GDAL.
"""

from .crs import same_grid, crs_of_prj, crs_of_shapefile, SAME_GRID
from .shapefile import read_shapefile, ShapefileError
from .layer import (add_gis_layer, gis_layers, GIS_FORMATS, inspect_layer, read_features,
                    format_of, bbox_wgs84)
from .geojson import read_geojson, GeoJsonError
from .geopackage import gpkg_layers, read_gpkg_layer, GeoPackageError
from .geotiff import read_geotiff_info, read_band, GeoTiffError
from .contours import contours, levels_for
from .landscape import add_landscape_surface, landscape_surfaces, add_contours
from .site import (add_site, sites, site_of, set_footprint, footprint_of,
                   footprint_from_glbs, plan_hull, PLACE_TYPES)
from .footprint import (FootprintRefused, footprint_verdict, may_have_footprint,
                        write_footprint, footprints, simplify_polygons,
                        footprint_from_proxy, top_outline)

__all__ = [
    "same_grid", "crs_of_prj", "crs_of_shapefile", "SAME_GRID",
    "read_shapefile", "ShapefileError",
    "add_gis_layer", "gis_layers", "GIS_FORMATS", "inspect_layer", "read_features",
    "format_of", "bbox_wgs84", "read_geojson", "GeoJsonError", "gpkg_layers",
    "read_gpkg_layer", "GeoPackageError", "read_geotiff_info", "read_band", "GeoTiffError",
    "contours", "levels_for", "add_landscape_surface", "landscape_surfaces", "add_contours",
    "add_site", "sites", "site_of", "set_footprint", "footprint_of",
    "footprint_from_glbs", "plan_hull", "PLACE_TYPES",
    "FootprintRefused", "footprint_verdict", "may_have_footprint", "write_footprint",
    "footprints", "simplify_polygons", "footprint_from_proxy", "top_outline",
]
