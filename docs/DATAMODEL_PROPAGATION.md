# Datamodel propagation

*Measured on 2026-09-30: node datamodel 1.6.17, connections 1.6.31, qualia
1.6.2, `em.ttl` 1.6.9, s3dgraphy 1.6.0.dev24. The fingerprint (§1) added on
2026-10-01: `sha256:12c5d520cf393be752360210a2a1ac7e74cac67169d18edfb005e250f6bd3b91`
at those versions.*

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
that someone runs. What each copy **can** do is check itself: every one of them
compares what it holds with the datamodel's fingerprint (§1) and names what
moved.

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
      │                                             + datamodel.fingerprint.json
      │                                             npm run check:datamodel
      └── registry-snapshot ► stratigraph-templates registry/s3dgraphy-snapshot.json
                                   │ validate / build stop if it diverges,
                                   │ naming the datamodel (fingerprint)
                                   ▼
                              dist/schede/<id>/<ver>.json   header (+ datamodel.digest)
                                   │                        + recipe (5 CRDT ops)
                                   │ sync-schede.sh
                                   ▼
                              StratiField   schede/  →  app/operazioni.plan()
                                   │ at load: header.datamodel vs its own s3dgraphy
                                   │ → a notice in the log and on the scheda
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

### The fingerprint: one digest for every copy

`api.datamodel_fingerprint()` (module `s3dgraphy.datamodel`) is **the identity of
the datamodel a consumer copies**. It covers exactly the six JSON files a
consumer copies, measured on 2026-10-01:

| Name | File | Version key | Copied by |
| --- | --- | --- | --- |
| `nodes` | `s3Dgraphy_node_datamodel.json` | `s3Dgraphy_data_model_version` | EMStudio, templates |
| `node_registry` | `node_registry.generated.json` | `s3Dgraphy_data_model_version` | EMStudio, templates |
| `connections` | `s3Dgraphy_connections_datamodel.json` | `s3Dgraphy_connections_model_version` | EMStudio, templates, Heriverse |
| `visual_rules` | `em_visual_rules.json` | `version` | EMStudio, Heriverse |
| `qualia` | `em_qualia_types.json` | `metadata.version` | EMStudio, templates, Heriverse |
| `translations` | `datamodel_translations.json` | `version` | EMStudio |

The other JSONs in `JSON_config` (document and extractor types, palette icons,
qualia additions) are read only inside this package and do not move the
fingerprint. `em.ttl` is not JSON: stratigraph-templates compares it term by
term.

It returns `{digest, versions, digests, files}`: `digest` is `sha256:<hex>` over
all six, `versions` one version per name, `digests` one digest per file, and
(since dev25) `files` the same facts per file, `{name: {file, digest, version}}`.
The per-file digests are what lets a copy whose version stayed and whose content
moved still be **named**.

**Each consumer is compared on what it reads.** The one digest says «the same
datamodel, all of it»: it is what a consumer that copies all six compares
(EMStudio). A consumer that reads only some files is compared on those and never
on the one digest: `api.datamodel_differences(expected, found, names)` and
`api.datamodel_fingerprint_subset(fp, names)`. stratigraph-templates reads
`nodes`, `node_registry`, `connections` and `qualia` (and `em.ttl`, term by
term), so a change to the visual rules or to the translations does not stop its
`validate`; a change to the nodes does, and names the file. `consumer_drift`
compares it on the same four.

**The canonical form is RFC 8785** (JSON Canonicalization Scheme): keys sorted by
UTF-16 code unit, no whitespace, strings escaped as `JSON.stringify` escapes them,
UTF-8, numbers as ECMAScript writes them. The files are canonicalised in order of
file name and the bytes concatenated. RFC 8785 because EMStudio computes the same
digest in JavaScript, and `em_visual_rules.json` holds 139 integral floats that
`json.dumps` writes `1.0` and `JSON.stringify` writes `1`.

`api.datamodel_differences(expected, found)` names each difference, the copy's
version first: `nodes 1.6.12 vs 1.6.17`, `visual_rules 1.6.27: same version,
different content`. Every consumer uses the same wording.

Guards: `tests/test_datamodel_fingerprint.py` (a reordered or reindented file
keeps the digest, a changed value moves it and names the file, RFC 8785 number
by number).

### `em.ttl` is aligned by hand, and compared whole

Every `em:` term a datamodel cites must be declared in `JSON_config/em.ttl`. The
declaration's comment says `Maps to: …`, and `owl:versionInfo` is raised with
the file. `tests/test_em_ttl_matches_the_datamodels.py` compares the two sets:
every value in the six datamodel JSONs that **is** an `em:` term (a class's
`uri`, an edge's `extension_mapping`, a `subclass_of`, …; prose is not read)
against every `em:` subject of `em.ttl`.

* **Cited but not declared** fails hard. Today: none.
* **Declared but cited by no datamodel** fails too, unless the term is in
  `EM_TTL_EXCEPTIONS` with its reason written (an exception without a reason
  fails, and so does one that has since become cited). Since 2026-10-26 (nodes
  1.6.18, connections 1.6.32, qualia 1.6.3) 30 of the 35 terms the code wrote
  without a citation are cited where they belong: the stamps, the tombstone,
  the AI marker and the verification as `properties` of the base `Node`; the
  AP11 subproperties as `mapping.subproperty` of each physical edge (the
  exporter's `AP11_SUBPROPS` is now read from there); the resource, shape,
  region, author and qualia terms on their classes. Since connections 1.6.33
  two more leave with the edge nearest to them: `derivedFromDocument` with
  `has_documentation` from a USD, `reconstructsFrom` with `is_part_of` SF → VSF
  read from the whole. The three exceptions left are terms of the EM theory
  (`hypothesizedBy`, `reconstructsAbsent`, `wasReusedFrom`) that no edge of the
  graph carries yet.

  **A new `em:` term** goes into `em.ttl` AND into the datamodel field the code
  writes it from, in the same change; the test says which one is missing.

Single alignments keep their targeted tests, for example
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

* **`registry/s3dgraphy-snapshot.json`** is the snapshot (format 4). It records:
  * the node, connections and qualia datamodels, `node_registry.generated.json`,
    and `em.ttl`'s version and terms;
  * `datamodel`: the fingerprint (§1), computed by s3Dgraphy, not restated;
  * `s3dgraphy.crdt.OPS` and the edges' RDF mapping;
  * the s3Dgraphy commit and dirty flag it was taken from.

  It is regenerated with `stratigraph-templates registry-snapshot`. s3Dgraphy is
  found through `$STRATIGRAPH_S3DGRAPHY_SRC`, else the sibling
  `../s3Dgraphy/src` (`registry.py` `_CANDIDATE_SRC`).
* **`validate` and `build` stop if the snapshot and the working tree diverge.**
  `registry()` compares content, not commits, fingerprint included. It raises
  `RegistryDivergence`, which exits with code 2 and lists each difference, the
  datamodels first: `datamodel: nodes 1.6.12 vs 1.6.17`. So a change to the visual
  rules or the translations alone also stops it: one fingerprint, one decision.
  A format-3 snapshot (before the fingerprint) is still read, so that its
  divergence is named. `--snapshot` (before the subcommand) compiles against the
  snapshot alone.
* **`stratigraph-templates build`** writes `dist/schede/<id>/<version>.json` and
  `dist/schede/index.json`. Each compiled sheet has a `header` and a `recipe`:
  * `header.datamodel` holds one version per datamodel, under the fingerprint's
    names (`nodes`, `node_registry`, `connections`, `visual_rules`, `qualia`,
    `translations`), **`digest`, the fingerprint**, and `em_ttl`, `s3dgraphy`,
    `taken_from`. `dist/schede/index.json` carries the fingerprint too.
  * `header.digest` is the sha256 **of the definition**. It excludes `datamodel`,
    so a datamodel change that leaves the recipe alone keeps the digest. Versions
    published before 2026-10-01 have no fingerprint and never will: a published
    version does not change.
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

* **At load, StratiField compares `header.datamodel`** (versions and
  fingerprint) with the s3dgraphy it carries (`app/scheda.py`
  `check_datamodel`). It **does not block**: the recipe is five operations the
  room applies with its own s3dgraphy. It makes the difference visible:
  * `differs`: a warning in the log, once per scheda version
    («costruita su un altro datamodel: nodi 1.6.12, qui 1.6.17»), and a notice on
    the scheda, in both views, drawn by `web/scheda.js` `datamodelNotice` from
    `for_browser()["datamodel_check"]`;
  * `no_digest` (a scheda compiled before the fingerprint): a softer notice, and
    `info` in the log;
  * `aligned`: nothing;
  * `unchecked`: this node's s3dgraphy cannot compute the fingerprint (a release
    older than `s3dgraphy.datamodel`).
* **`sync-schede.sh`** prints the fingerprint of the latest version of each
  vendored scheda and that of the installed s3dgraphy.

## 4 · The other tools

* **EMStudio.** The frontend cannot import Python, so it vendors.
  `frontend/scripts/sync-datamodels.sh [path]` (or `./em.sh sync`) copies the
  datamodel JSONs, `node_registry.generated.json` and `datamodel_translations.json`
  into `frontend/src/assets/`. It also writes
  `crates/em-core/assets/em_visual_rules.core.json` (the visual rules without
  `2d_glyphs`) and the 2D icons and DTC glyphs, and
  `frontend/src/assets/datamodel.fingerprint.json`: the fingerprint of what it
  copied, recomputed in JavaScript (`frontend/scripts/datamodel-fingerprint.mjs`).
  **`npm run check:datamodel`** (`frontend/scripts/check-datamodel.mjs`) fails,
  naming the datamodel, when the copies no longer match that file (edited by
  hand) or no longer match the sibling s3Dgraphy working tree; with a python
  that has `s3dgraphy.datamodel` it also checks the JavaScript digest against the
  Python one. Its Python sidecar separately pins s3dgraphy in
  `tools/requirements.txt`.
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
| 2 | Declare every new `em:` term in `em.ttl`, with `Maps to:`; raise `owl:versionInfo` | edit `em.ttl` | `tests/test_em_ttl_matches_the_datamodels.py` (a cited term not declared; a new declared term no datamodel cites) |
| 3 | Regenerate the node registry (node classes changed) | `python -m s3dgraphy.tools.sync_node_datamodel` | `tests/test_node_datamodel_registry.py::test_node_registry_in_sync` |
| 4 | Regenerate the glyphs (an SVG changed) | `python -m s3dgraphy.tools.glyphs_from_svg --write` | `tests/test_glyph_paths.py` |
| 5 | Reseed the English translations (a label or description changed) | `python -m s3dgraphy.tools.datamodel_i18n seed` | `tests/test_datamodel_i18n.py::test_committed_sidecar_en_is_in_sync` |
| 6 | Re-stamp the shipped mappings that you checked | `api.mapping_stamp(mapping)` | `tests/test_shipped_mappings.py` (validation; a stale stamp only warns) |
| 7 | Run the suite | `python -m pytest` | — |
| 8 | See who is behind | `python -m s3dgraphy.tools.consumer_drift` · `python -m s3dgraphy.tools.wheel_drift` | `--check` exits 1 for a consumer this project owns and tracks (EMStudio, stratigraph-templates) that is behind or holds an edited copy; every datamodel and the fingerprint are compared, each difference named |

**In the consumers**, from the parent directory that holds the checkouts:

| # | Repository | Command | Red if skipped |
| --- | --- | --- | --- |
| 9 | EMStudio | `cd EMStudio/frontend && ./scripts/sync-datamodels.sh`, then review and commit the diff (the copies and `datamodel.fingerprint.json`) | `npm run check:datamodel`; `consumer_drift --check`; `cargo test -p em-core --test visual_rules_core` if the visual rules changed |
| 10 | EM-blender-tools | `cd EM-blender-tools && ./em.sh rebundle` (then `./em.sh manifest 3.11` / `3.13` if the wheel name changed) | `wheel_drift --check` |
| 11 | stratigraph-templates | `cd stratigraph-templates && .venv/bin/stratigraph-templates registry-snapshot`, read the diff of `registry/`, then `.venv/bin/stratigraph-templates build` (a datamodel-only change rewrites the current sheets' `header.datamodel`, same digest) | `validate` exits 2 naming the datamodel; `tests/test_registry.py::test_the_committed_snapshot_is_what_s3dgraphy_declares_today`; every test using the `reg` fixture errors at setup; then `tests/test_build.py::test_the_committed_dist_is_what_the_definitions_compile_to`, and `tests/test_datamodel_fingerprint.py`. Not `test_golden_iccd`: since templates `bdb09e4` the golden file leaves out `header.datamodel` and `header.compiled_by`, so it moves with a recipe (step 12) and never after a snapshot |
| 12 | stratigraph-templates, if a recipe changed | raise `template.version`, `build` again; refresh the golden file with `STRATIGRAPH_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_build.py::test_golden_iccd` | `PublishedVersionChanged` from `build`; `tests/test_build.py::test_golden_iccd` |
| 13 | StratiField | `cd stratigraph-chatbot && ./sync-schede.sh` (it prints both fingerprints) | `tests/test_la_scheda_diventa_operazioni.py::test_the_vendored_copy_is_the_compiled_form_and_not_stale` (only when the sibling `dist/` exists); at run time, the notice on every scheda whose fingerprint is not the node's |
| 14 | StratiGraph Server, EMStudio sidecar | after a PyPI release: `./bump-s3dgraphy.sh <ver>` in the server; the pin in `EMStudio/tools/requirements.txt` | nothing automatic |

A consumer somebody else owns (Heriverse) being behind is **news to send**, not a
task. `consumer_drift` reports it and exits 0.

After step 8, the publication and steps 9–14 run in one command from s3Dgraphy,
which stops where a person is needed and resumes where it stopped:
`./em.sh release <version> [--dtcstamp X] [--desktop]` (`--dry-run` shows each
step with its verdict; `./em.sh release status` says where a round stands;
`./em.sh help release` lists the eleven steps).
