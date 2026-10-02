# metashape_min — a Metashape project reduced to five cameras

The `doc.xml` files of San Pietro (`sanpietro_LOD0.psx`, chunk 1 «Chunk 1_LOD0»,
Metashape 2.3.0.21954, 22-23 July 2026), copied on 02-10-2026 and reduced:

| file | from | reduced to |
|---|---|---|
| `project.xml` | `project.zip` | unchanged (the test keeps chunk 1 only) |
| `chunk.xml` | `1/chunk.zip` | cameras 2, 3, 4 (drone), 71 (Canon, aligned), 171 (Canon, not aligned); no covariances |
| `frame.xml` | `1/0/frame.zip` | the same five cameras (paths and EXIF as written); marker projections on them only (none) |
| `tie_points.xml` | `1/0/point_cloud/point_cloud.zip` | projections of the five cameras; tracks and points counts as written |
| `depth_maps.xml` | `1/0/depth_maps/depth_maps.zip` | one block |
| `depth_maps_block.xml` | `1/0/depth_maps/data1.zip` | the depth maps of cameras 2, 3, 4 |
| `model_1.xml`, `model_2.xml` | `1/0/model/model.zip`, `1/0/model.1/model.zip` | unchanged |

The photo paths are the project's own relative ones (`../../../Segni_Acropoli_drone/…`,
`../../../Canon 6D 24mm/…`): no personal path, nothing from `01_input_sources/`
(checked with grep). The meshes are not here: `tests/test_metashape_project.py`
writes a `mesh.ply` with only the header, carrying the real counts.
