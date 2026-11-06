"""The ground surface of a landscape, as a node — MICRO-GIS-BASE (6 Nov 2026).

A DEM and, over it, an orthophoto are two GIS layers (``ResourceNode`` of
url_type ``gis_layer``, a GeoTIFF each). What they make TOGETHER — the surface
the site stands on, drawn as a mesh with its texture — is a statement about
the place, and it needs a node to be said: which DEM, which image, at what
step, for which site.

Why not a ``RepresentationModelNode``: an RM is the 3D representation OF A
STRATIGRAPHIC NODE (its datamodel definition, «always linked to the
represented node via P138»); the ground of a landscape is not a unit, and a
Space would look for its glTF versions. Why not the ``LocationNodeGroup``
itself: the manual is explicit, «a location is identitary, not geometric» —
the place is the identity, this is one of its geometries (``P161 has spatial
projection`` in the CIDOC reading of the site page).

The node hats its layers with ``has_linked_resource`` (the elevation is the
layer whose ``data.raster.kind`` is ``dem``, the texture an ``image`` one); a
reader that does not know it sees a node with two resources. ``data``:

* ``step_m`` — the side of the mesh's cells in the scene (metres), chosen by
  whoever made it; absent = the DEM's own pixel;
* ``vertical_exaggeration`` — 1 unless said (a surface is drawn true);
* ``note`` — free.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base_node import Node


class LandscapeSurfaceNode(Node):
    node_type = "landscape_surface"

    def __init__(self, node_id: str, name: str = "Landscape surface",
                 description: str = "", step_m: Optional[float] = None,
                 vertical_exaggeration: Optional[float] = None,
                 data: Optional[Dict[str, Any]] = None):
        super().__init__(node_id=node_id, name=name, description=description)
        self.data = dict(data or {})
        if step_m is not None:
            if not isinstance(step_m, (int, float)) or isinstance(step_m, bool) or step_m <= 0:
                raise ValueError(f"step_m must be a positive number of metres, got {step_m!r}")
            self.data["step_m"] = float(step_m)
        if vertical_exaggeration is not None:
            if not isinstance(vertical_exaggeration, (int, float)) or vertical_exaggeration <= 0:
                raise ValueError("vertical_exaggeration must be a positive number")
            self.data["vertical_exaggeration"] = float(vertical_exaggeration)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "name": self.name,
                "description": self.description, "data": self.data}
