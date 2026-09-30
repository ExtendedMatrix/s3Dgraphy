# Datamodel propagation

*Measured on 2026-09-30: node datamodel 1.6.17, connections 1.6.31, qualia
1.6.2, `em.ttl` 1.6.9, s3dgraphy 1.6.0.dev24.*

[Source of truth](SOURCE_OF_TRUTH.md) says **where** a name is declared, and
that the arrow points one way. This page follows the arrow **out of the
repository**: what happens, and what must be done by hand, between a change to a
datamodel JSON and the moment every tool reads it.

Each tool holds the datamodel in one of three ways, and that decides what you
have to do:

* it **imports the package**, so it moves when its pin moves (StratiGraph
  Server, PyArchInit);
* it **bundles a wheel**, so it moves when the wheel is rebuilt
  (EM-blender-tools);
* it **vendors a copy** of the JSON files or of something derived from them, so
  it moves when a sync script runs and the diff is committed (EMStudio,
  stratigraph-templates, StratiField).

No tool reads another repository at run time. So every arrow below is a step
that someone runs.

## The chain

```text
 s3Dgraphy (this repository)
 ───────────────────────────────────────────────────────────────────────────────
  JSON_config/*.json ── the datamodel, the source of truth
      │   by hand
      ├──────────► JSON_config/em.ttl          (ontology, aligned with care)
      │   code reads the JSON
      ├──────────► importers / exporters / crdt / api
      │   translated in data
      └──────────► mappings/  (pyArchInit, EMdb, xlsx, source lists)
                     └ each carries a _validated_against stamp
      │
      │ the tools
      ├── pip pin ──────────► StratiGraph Server   em.apply_op, LWW per field
      ├── pip / aux file ───► PyArchInit           a contributor: its table enters em.json
      ├── wheel ────────────► EM-blender-tools     graph editor filter, via get_connections_datamodel()
      ├── sync-datamodels.sh► EMStudio             frontend/src/assets/*.json
      └── registry-snapshot ► stratigraph-templates registry/s3dgraphy-snapshot.json
                                   │ validate / build stop if it diverges
                                   ▼
                              dist/schede/<id>/<ver>.json   header + recipe (5 CRDT ops)
                                   │ sync-schede.sh
                                   ▼
                              StratiField   schede/  →  app/operazioni.plan()
                                   │ the same op list, three transports
                                   ├── websocket (seated)       ─┐
                                   ├── POST /v1/rooms/{id}/ops  ─┼─► StratiGraph Server
                                   └── local em.json container    (apply_op_to_section)
```

## 1 · Inside s3Dgraphy

### The datamodel JSON is the truth

The four files and what each declares are listed in
[Source of truth §1](SOURCE_OF_TRUTH.md). Every datamodel file carries its own
version key (`s3Dgraphy_data_model_version`, `s3Dgraphy_connections_model_version`,
`em_visual_rules.json` `version`, `datamodel_translations.json` `version`).
Every change raises that version and says why in the file's `description`.
[Updating the mapping](mapping-update-procedure.rst), step 7, explains why the
reason goes in the file and not in a commit message.

Two files are **generated** next to the hand-written ones, and each has a check
that fails when it drifts:

| Generated file | From | Regenerate | Guard |
| --- | --- | --- | --- |
| `node_registry.generated.json` | the Python node classes | `python -m s3dgraphy.tools.sync_node_datamodel` | `tests/test_node_datamodel_registry.py::test_node_registry_in_sync` |
| `em_visual_rules.json` → `2d_glyphs` | the SVGs in `JSON_config/src/2D/` | `python -m s3dgraphy.tools.glyphs_from_svg --write` | `tests/test_glyph_paths.py` |

`datamodel_translations.json` is hand-translated, but its English column is
seeded from the datamodels. `python -m s3dgraphy.tools.datamodel_i18n --check`
says whether it still matches, and
`tests/test_datamodel_i18n.py::test_committed_sidecar_en_is_in_sync` fails when
it does not.

### `em.ttl` is aligned by hand

Every `em:` term a datamodel cites must be declared in `JSON_config/em.ttl`. The
declaration's comment says `Maps to: …`, and `owl:versionInfo` is raised with
the file. **No test compares the whole of `em.ttl` with the datamodels.** Only
single alignments have targeted tests, for example
`tests/test_physical_relation_spellings.py::test_em_ttl_names_the_same_edges_the_datamodel_maps`
and `tests/test_unit_definition.py::test_em_ttl_declares_the_companion_subproperty`.
Checking the CIDOC-family IRIs against the official releases is a script run by
hand ([Updating the mapping](mapping-update-procedure.rst), step 4).

Downstream, `em.ttl` matters beyond RDF: stratigraph-templates records its
`owl:versionInfo` and its declared terms in its snapshot. So an `em.ttl` edit
alone is enough to make that repository stop (§2).

### The code reads the JSON

Importers, exporters, the CRDT and `api` ask the datamodel. For edges the one
door is `edges/connections_loader.py`, reached through
`get_connections_datamodel()`. The questions it answers are tabled in
[Source of truth §3](SOURCE_OF_TRUTH.md).

**Older spellings are read, never written.** An edge entry with
`spelling_of: <canonical>` is the same relation under an older name:

* `ConnectionsDatamodel.spellings(name)` returns every name a reader must
  recognise;
* `ConnectionsDatamodel.normalize_edge_name(name)` returns the one name a writer
  writes.

Guards: `tests/test_one_spelling_writers.py`, `tests/test_physical_relation_spellings.py`.

### The mappings speak to other datamodels

`src/s3dgraphy/mappings/` translates someone else's vocabulary (pyArchInit, EMdb,
xlsx, source lists) into the datamodel. Each mapping carries a
`_validated_against` stamp with the node and connections datamodel versions it
was checked against. `api.mapping_stamp(mapping)` validates a mapping and
returns a stamped copy. `api.mapping_stamp_check(mapping)` warns, and never
refuses, when a stamp is older than the build.
`tests/test_shipped_mappings.py::test_every_shipped_mapping_validates` validates
every shipped mapping.

### Worked example: adding `definition` to the US node

Commit `f0de0a1` added the *definition* of a stratigraphic unit (the DEFINIZIONE
box of the Italian US sheet). It is an element of the node, not a qualia. These
are the places it had to reach:

1. **Datamodel.** `s3Dgraphy_node_datamodel.json`, under
   `stratigraphic_nodes.StratigraphicNode.properties.definition`, as an object
   with `kind: node_element`, `value: concept`, `em_json: data.definition` and an
   `rdf` block (`with_concept: crm:P2_has_type`, `concept_class: crm:E55_Type`,
   `label_only: null`, `specialised_alternative: em:hasDefinition`). It is
   declared **once**, on the parent class, and every stratigraphic subtype
   inherits it. The version went 1.6.8 → 1.6.9.
2. **`em.ttl`.** `em:hasDefinition`, a subproperty of `crm:P2_has_type`, with
   `Maps to: node_datamodel StratigraphicNode.properties.definition`. It is
   declared but not emitted by default. `owl:versionInfo` was raised.
3. **Code.**
   * `nodes/stratigraphic_node.py`: `definition_parts()` reads `{concept, label}`.
   * `exporter/emjson_exporter.py`: `definition` joins `_LIFTED_ATTRS`, so it
     travels as `data.definition`.
   * The RDF exporter and importer read the `rdf` block through
     `_Datamodel.get_node_element_rule(node, "definition")`, which walks the class
     hierarchy.
   * No change to `crdt.py`. `update_field` already addresses every
     `data.<key>`.
4. **Mappings.** The shipped mappings' stamps were raised to node datamodel
   1.6.9.
5. **Tests.** `tests/test_unit_definition.py` follows the same order: the
   datamodel, then `em.ttl`, then em.json, the CRDT and RDF.

The consumers followed separately. stratigraph-templates reads node elements
from the snapshot (`node_elements`, `registry.py` `_node_elements()`), so the ICCD
sheet's `definizione` field compiles to
`update_field data.definition`. StratiField then vendors that sheet.

## 2 · stratigraph-templates

A recording sheet is data. It is compiled against a **snapshot** of the
datamodel, not against the live checkout, so a datamodel change reaches a sheet
only when someone decides it should.

* **`registry/s3dgraphy-snapshot.json`** is the snapshot. It records:
  * the node, connections and qualia datamodels, `node_registry.generated.json`,
    and `em.ttl`'s version and terms;
  * `s3dgraphy.crdt.OPS` and the edges' RDF mapping;
  * the s3Dgraphy commit and dirty flag it was taken from.

  It is regenerated with `stratigraph-templates registry-snapshot`. s3Dgraphy is
  found through `$STRATIGRAPH_S3DGRAPHY_SRC`, else the sibling
  `../s3Dgraphy/src` (`registry.py` `_CANDIDATE_SRC`).
* **`validate` and `build` stop if the snapshot and the working tree diverge.**
  `registry()` compares content, not commits. It raises `RegistryDivergence`,
  which exits with code 2 and lists each difference. `--snapshot` (before the
  subcommand) compiles against the snapshot alone.
* **`stratigraph-templates build`** writes `dist/schede/<id>/<version>.json` and
  `dist/schede/index.json`. Each compiled sheet has a `header` and a `recipe`:
  * `header.datamodel` holds the datamodel versions it was compiled against
    (`nodes`, `connections`, `qualia`, `em_ttl`, `s3dgraphy`, `taken_from`).
  * `header.digest` is the sha256 **of the definition**. It excludes `datamodel`,
    so a datamodel change that leaves the recipe alone keeps the digest.
  * `recipe.operations` is the five CRDT operations, copied from the snapshot:
    `add_node`, `update_field`, `remove_node`, `add_edge`, `remove_edge`.
  * A published version never changes. If a new compile of the same version has a
    different digest, `build` raises `PublishedVersionChanged`. Raise
    `template.version` and build again.

## 3 · StratiField (`stratigraph-chatbot`)

* **`./sync-schede.sh [path]`** vendors `stratigraph-templates/dist/schede/` into
  `schede/`. With no argument it uses the sibling checkout. It also resolves the
  vocabularies into `vocabolari/` using the templates' own Python, and writes the
  licence notices.
* **`app/operazioni.py` `plan()`** turns a sheet's recipe and the recorder's
  values into a list of operations. It is a pure function: it reads the room's
  section and never writes it. It always stamps `data.scheda` =
  `{template, version, digest}` on the unit.
* **The same list goes out by three transports** (`app/writer.py`):
  * the websocket, for a seated scribe (`RoomWriter._send_seated`);
  * `POST /v1/rooms/{id}/ops`, the correspondent and queue path (`_post_ops`);
  * a local em.json container (`LocalWriter.send`), which applies each op with
    `s3dgraphy.crdt.apply_op_to_section`.
* **The return is the recipe read backwards.** `values_from_graph()` walks the
  same recipe, and the marks `data.scheda` and `data.scheda_links.<field>`, from
  the graph back to the sheet.

StratiField does **not** compare `header.datamodel` with anything at run time.
It stores the header, and the digest travels only as provenance on the unit.

## 4 · The other tools

* **EMStudio.** The frontend cannot import Python, so it vendors.
  `frontend/scripts/sync-datamodels.sh [path]` (or `./em.sh sync`) copies the
  datamodel JSONs, `node_registry.generated.json` and `datamodel_translations.json`
  into `frontend/src/assets/`. It also writes
  `crates/em-core/assets/em_visual_rules.core.json` (the visual rules without
  `2d_glyphs`) and the 2D icons and DTC glyphs. Its Python sidecar separately pins
  s3dgraphy in `tools/requirements.txt`.
* **EM-blender-tools.** No copy of the JSON. The graph editor reads the installed
  package: `graph_editor/utils.py` `get_connection_rules()` calls
  `get_connections_datamodel()`, and `with_spellings()` asks `spellings()`.
  `graph_editor/socket_generator.py` `load_datamodels()` opens the JSON files
  inside the package. The package is a wheel listed in `blender_manifest.toml`.
  `./em.sh rebundle` rebuilds it from `../s3Dgraphy`
  (`scripts/rebundle_s3dgraphy.py`). If the wheel's file name changed, run
  `./em.sh manifest 3.11|3.13` too.
  * **Caution:** the filter's categories (`STRATIGRAPHIC_RELATIONS` and the
    lists in `graph_editor/properties.py`) are still written by hand. A new edge
    type appears in the filter, but under "other".
* **StratiGraph Server.** The orchestrator of a room. It applies every op with
  `em.apply_op` (`app/rooms.py`, `from s3dgraphy import api as em`). That calls
  `crdt.apply_op_to_section`, and the result is last-writer-wins per field on
  the clock `(ts, author)`. The merge lives in s3Dgraphy, not in the server. The
  server moves with its s3dgraphy pin, and `./bump-s3dgraphy.sh <ver>` updates
  it. So a datamodel change reaches the server only after a release on PyPI.
* **PyArchInit.** A contributor. Its US table enters the graph in two ways:
  * as the graph itself, through `importer/pyarchinit_importer.py`
    (`PyArchInitImporter`, mapping `mappings/pyarchinit/pyarchinit_us_mapping.json`),
    and from there to em.json;
  * as an **auxiliary file** that only enriches existing units
    (`transforms/aux_tracking.py`; in EMtools, `aux_import.py`
    `import_pyarchinit_as_auxiliary()`).

  The two-way bridge with its database is `s3dgraphy.sync`. The mapping's stamp
  says which datamodel it was checked against.

## Checklist: I changed the datamodel. What now?

Run the commands in order. The last column is what goes red if you skip the step.

**In s3Dgraphy**, from the repository root, with `PYTHONPATH=src` or an
editable install:

| # | Step | Command | Red if skipped |
| --- | --- | --- | --- |
| 1 | Raise the file's version and say why in its `description` | edit the JSON | review; `stratigraph-templates` diffs name the versions |
| 2 | Declare every new `em:` term in `em.ttl`, with `Maps to:`; raise `owl:versionInfo` | edit `em.ttl` | a targeted `test_em_ttl_*` test, if you wrote one; there is no general one |
| 3 | Regenerate the node registry (node classes changed) | `python -m s3dgraphy.tools.sync_node_datamodel` | `tests/test_node_datamodel_registry.py::test_node_registry_in_sync` |
| 4 | Regenerate the glyphs (an SVG changed) | `python -m s3dgraphy.tools.glyphs_from_svg --write` | `tests/test_glyph_paths.py` |
| 5 | Reseed the English translations (a label or description changed) | `python -m s3dgraphy.tools.datamodel_i18n seed` | `tests/test_datamodel_i18n.py::test_committed_sidecar_en_is_in_sync` |
| 6 | Re-stamp the shipped mappings that you checked | `api.mapping_stamp(mapping)` | `tests/test_shipped_mappings.py` (validation; a stale stamp only warns) |
| 7 | Run the suite | `python -m pytest` | — |
| 8 | See who is behind | `python -m s3dgraphy.tools.consumer_drift` · `python -m s3dgraphy.tools.wheel_drift` | `--check` exits 1 for a consumer this project owns |

**In the consumers**, from the parent directory that holds the checkouts:

| # | Repository | Command | Red if skipped |
| --- | --- | --- | --- |
| 9 | EMStudio | `cd EMStudio/frontend && ./scripts/sync-datamodels.sh`, then review and commit the diff | `consumer_drift --check` (connections version only); `cargo test -p em-core --test visual_rules_core` if the visual rules changed |
| 10 | EM-blender-tools | `cd EM-blender-tools && ./em.sh rebundle` (then `./em.sh manifest 3.11` / `3.13` if the wheel name changed) | `wheel_drift --check` |
| 11 | stratigraph-templates | `cd stratigraph-templates && .venv/bin/stratigraph-templates registry-snapshot`, read the diff of `registry/`, then `.venv/bin/stratigraph-templates build` | `tests/test_registry.py::test_the_committed_snapshot_is_what_s3dgraphy_declares_today`; every test using the `reg` fixture errors at setup; then `tests/test_build.py::test_the_committed_dist_is_what_the_definitions_compile_to` |
| 12 | stratigraph-templates, if a recipe changed | raise `template.version`, `build` again; refresh the golden file with `STRATIGRAPH_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_build.py::test_golden_iccd` | `PublishedVersionChanged` from `build`; `tests/test_build.py::test_golden_iccd` |
| 13 | StratiField | `cd stratigraph-chatbot && ./sync-schede.sh` | `tests/test_la_scheda_diventa_operazioni.py::test_the_vendored_copy_is_the_compiled_form_and_not_stale` (only when the sibling `dist/` exists) |
| 14 | StratiGraph Server, EMStudio sidecar | after a PyPI release: `./bump-s3dgraphy.sh <ver>` in the server; the pin in `EMStudio/tools/requirements.txt` | nothing automatic |

A consumer somebody else owns (Heriverse) being behind is **news to send**, not a
task. `consumer_drift` reports it and exits 0.
