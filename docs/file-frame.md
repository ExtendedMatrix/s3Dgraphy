# The frame of a file

*Nodes datamodel 1.6.38 — MICRO tileset, shift e epoche, decided by E.D. on 25 Oct 2026.*

Many surveys (TLS, RealityScan, Metashape) export **shifted** coordinates while
declaring them in the project's CRS. The Basilica Iulia's RealityScan tileset
was written as E − 291407, N − 4640813 and declared as EPSG:6708 (RDN2008 /
UTM 33N), so its `root.transform`, read as ECEF, falls on the equator
(lat 0.0001°, lon 10.5115°).

`data.frame` says it once, on the node, so every tool reads it from the em.json:

```json
"frame": {"crs": "EPSG:6708", "shift": [291407.0, 4640813.0, 0.0],
          "note": "SHIFT6708.txt of the study", "source": "file"}
```

*The coordinates of this file are CRS X minus shift S.*

| key | what it says |
|---|---|
| `crs` | the CRS the coordinates are declared in, `EPSG:<code>` |
| `shift` | `[sx, sy, sz]`, metres: the file holds CRS coordinates minus this |
| `note` | optional: where the shift comes from |
| `source` | optional: `manual`, `graph` (the study's `geo_position`), `file` (a shift file) |

**Where it is looked for** (`s3dgraphy.geometry.frame.frame_of`): first the
resource, then its asset (a version inherits it, as it inherits the hat), then
its hat (the RM, or the RM container whose alternative it is).
`RepresentationModelNode` and `RepresentationModelNodeGroup` accept the same
field.

**It is a reading, never a rewrite.** A viewer that knows the frame relocates
the file and leaves it as it is. `relocate_transform` does this for a 3D Tiles
tileset:

1. it reads the points of the root's volume through the written
   `root.transform` (ECEF);
2. it goes back to the shifted coordinates with the inverse of the same
   projection;
3. it adds the shift;
4. it fits the affine transform that maps the tileset's own frame to ECEF (a
   globe) or to the local frame of a study (its CRS minus its shift).

The residual of the fit is returned in metres. On the Basilica it is 0.03 mm
to ECEF and 0.6 mm to the study's frame, measured on 125 points. The true
transform carries UTM's scale at the equator (1.0027). A viewer that only moves
the tileset, without that scale, makes the Basilica 25 cm shorter over its
188 m.

**Z.** The third number of the shift is added to the height the file carries.
The height system (ellipsoidal or orthometric) is not declared in the frame.

The frame is not projected to RDF: it is a reading aid for the tools.
