# em.json conformance suite

CC0 1.0. Six files, each with the result a conforming reader obtains
(`expected/<name>.json`, written by `reference_reading.py`, standard library
only, no implementation inside).

| File | Case |
|---|---|
| `01-minimal.em.json` | one graph, two units, one relation |
| `02-multigraph.em.json` | two study graphs with their own layouts, a link between them, the shelf |
| `03-georeferenced.em.json` | a geo-position (EPSG:3844 and shift) and a 3D model as a resource |
| `04-horizons.em.json` | the periodizations member: a periodization and its horizons; a derived `is_after` with its origin |
| `05-legacy-v1-flat.em.json` | the flat form of 1.0, still read |
| `06-unknown-keys.em.json` | `x-` keys at every level, a node of an unknown type, a member with an unknown marker |

The expected reading lists, per graph: its role (study, shelf, dtc,
periodizations), its nodes with their types, its edges, its links; and the
active graph. `must_survive_round_trip` names the keys a writer must carry
through (header keys it does not own, a node's data, an edge's attributes).

A reader conforms when its reading equals the expected one — it may add the
default geo-position node of a graph, nothing else. A writer conforms when what
it writes validates against `em.v1.1.schema.json` and, read again, gives the same
reading with every node's name, description and data and every edge's attributes
unchanged.

    python reference_reading.py --check     # the expected files are up to date

Implementations: s3Dgraphy `tests/test_emjson_conformance.py`; EMStudio
`frontend/scripts/check-emjson-conformance.mjs`.
