# Changelog

All notable changes to **s3dgraphy** are documented here.

## [Unreleased] — after 1.6.0.dev34 (MICRO un solo vocabolario, 4 October 2026)

### Added
- **A property as a source** (connections 1.6.36, MICRO «la proprietà come
  fonte», decided by E.D. 9 October 2026: the trusses take the wood species of
  the fragments found, the upper parts of a temple the material of the lower
  ones). One extracts from the PROPERTY, not from the unit: the reader's
  extractor is `extracted_from` the MASTER — the property in its own unit — as
  it is a document. New module `s3dgraphy.property_source`;
  `api.owner_unit_of`, `api.read_property`.
  `extracted_from.target += PropertyNode` (`_note_property` WIDENED,
  `property_source_note`). The new block `paradata_reasoning` holds the EM
  words of the reasoning between properties, translated in
  `datamodel_translations.json` 1.7, section `reasoning` (en/it/de;
  `datamodel_i18n.reasoning_text`). A line from an extractor to a property is
  also what an old yEd provenance line drawn backwards looks like:
  `property_source.reads_as_source` tells them apart from the graph (a reading
  is an extractor that feeds ANOTHER property), and
  `connection_resolver.candidate_edge_types(..., graph=)` names
  `extracted_from` only then; without the graph it does not.
- **The instance is a view** (connections 1.6.37, translations 1.8,
  em_visual_rules 1.6.33, MICRO «l'istanza è una
  vista», decided by E.D. 9 October 2026, evening: «non ha nessun senso fare
  un'istanza nel triple store: è solamente una modalità grafica di
  rappresentare il grafo»). No instance node in em.json nor in the RDF: for a
  paradata group, every master outside it — a document or a property — that a
  reader of the group reaches is DRAWN inside it, with the badge of where it
  comes from (the property's unit, the document's epoch). One rule for every
  client, the block `paradata_instances` of `em_visual_rules.json`, read by the
  pure function `s3dgraphy.paradata_view.view_instances(graph, group_id)`
  (`api.view_instances`), which also gives the instance's id
  (`<master>##<group>`). A property instance STORED in the afternoon of the same
  day (a `PropertyNode` with `data.instance_of`) is folded onto its master when
  an em.json is read (`property_source.fold_stored_instances`, one warning
  line); the afternoon's `instantiate_property`, `master_of`, `instances_of`
  and `refresh_instance` are gone. A new connections version rather than
  1.6.36 revised in place: EMStudio had already vendored the afternoon's
  1.6.36, and one version must mean one content. In `paradata_reasoning`
  `property_instance` becomes `instance`, the badge says `{owner}` (a unit, or
  the epoch of a document), `refresh_instance` goes; the nine shipped mappings
  are re-stamped against 1.6.37.
- **The value read, and «the source has changed»** (MICRO «la proprietà come
  fonte», part 2). `read_property` keeps on the extractor what it read, flat
  like the passage a region quotes: `data.read_value` (the master's value) and
  `data.read_at`; asked again it re-reads. The diagnostic `source_changed`
  (`property_source.source_changed`, among the warnings of `api.validate`):
  the master's value is no longer the one the extractor read; it says so
  until a person re-reads. `api.reasoning_diagnostics` gives the records, each
  with the `code` of its words in the translations.
- **Who leans on what, and «source removed»** (MICRO «la proprietà come fonte»,
  part 3). `dependents_of(graph, node_id)`: for a unit, a property or a document,
  the chains that lean on it in cascade — its own properties,
  extractors, combiners, regions, the properties of other units, the heirs —
  each with its kind, the node it leans on and its depth (nothing similar
  existed: `diagnostics` attributes claims and finds stratigraphic cycles).
  `remove_keeping_trace`: the node stays with its name and last value, marked
  as the CRDT marks a deletion (`data.removed = {ts, by}`), the edges towards it
  live; em.json and the RDF round trip keep it, GraphML / Heriverse / RDF publish
  leave it out (`dissemination.live_view`), and the diagnostic `source_removed`
  names who still leans on it. `remove_cascade`: the node and what depends ONLY
  on it, the properties of other units kept and reported (`orphaned` when left
  without provenance). `reasoning_cycle`: a reasoning that comes back to itself,
  as the list of its properties. `crdt.compact_section` keeps a tombstoned node
  a live edge still reaches (it dropped it and left the edge dangling).
- **Two owners nobody declared: «Declare the inheritance»** (MICRO «la proprietà
  come fonte», part 4). The diagnostic `undeclared_owners` — two or more
  `has_property` not marked `inherited` — brought here from EMStudio's
  `compact.undeclaredOwners` (s3Dgraphy had the listing
  `ownership.shared_properties`, no diagnostic). Its two cures:
  `declare_inheritance(graph, property_id, original_owner_id)` marks the other
  owners `inherited` and moves the property, with the chain that serves only
  it, to the original owner's paradata group (the rule of `ownership.py`);
  `duplicate_per_owner(graph, property_id)` follows EMStudio's
  `duplicateForEachOwner` — combiners and extractors duplicated, the copies
  reading the same masters (documents, properties) as they are.
- **A version of several files, and a version made again** (MICRO «i parametri
  diventano la ricetta della versione», E.D. 6 October 2026: for Heriverse/ATON
  the version is a glTF with its textures). `add_version` with several files
  (`packaging: file_set`) gives the version the url of its entry point — the
  `.gltf` a reader opens, where Heriverse looks (`data.url`) — and its media
  type; its checksum is the members digest, and adding the same set again is
  recognised by that digest (it compared the door's sha256 with the set's and
  refused the same bytes). `versions_of` takes the url from the entry point
  when the resource has none. `add_version(…, revise=True)`: other bytes at a
  level whose version shares the use make a REVISION of it — a new resource
  `was_revision_of` the version there, made by its own `lod_generation` step —
  and `versions_of` / `version_for` give the revision (the glb made for
  Heriverse on 6 October becomes a glTF with its textures at the same level).
  `planned_version` says the id before anything is written, so a tool can stamp
  a version before it is born. Tests in `test_asset_versions.py`.
- **The glyphs of the 3D objects** (em_visual_rules 1.6.32, MICRO grafo
  reattivo G9, 9 October 2026; drawings approved by E.D. on 6 October). The
  three Representation Models (`representation_model`, `_doc` — the checkered
  picture seen three-quarters, an image placed in 3D space — and `_sf`) get
  their own pictograms in place of three identical Font Awesome cubes and join
  `2d_render_glyph_types.types`; `proxy`, `tileset`, `container` (the RM
  container) and the versions `version:gltf`, `version:mesh`, `version:tiles`,
  `version:scene` come from the new table `2d_render_glyph_types.data_glyphs`,
  which resolves a node by its data (node type, `data.*`, the URL's extension or
  name), keyed like `dtc:<kind>`; the rule for a version's kind was measured on
  Templu Mare v2, where no resource carries a `data.format`. All in the DTC
  frame with the 2×2 checker of the EMtools icons (`accent`, never recoloured).
  `glyphs_from_svg` turns `data-frame="true"` into `frame: true` layers and
  writes each entry's `frameless_box`, so a consumer can draw the glyph without
  its circle below 24 px (`docs/drawing-a-glyph.md` §5); `glyph_sheet` shows the
  two variants side by side.
- **The index stays alive** (MICRO l'indice del grafo, 7 October 2026, issue
  #27 by Enzo Cocca: a 990-US pyArchInit site imported in 8.7 s and its GraphML
  export did not finish in 30 minutes). `find_node_by_id` and `find_edge_by_id`
  answer in O(1) always, from id maps `add_node` (with `overwrite=True` too)
  and `add_edge` keep up to date; the list setters, `remove_*`,
  `invalidate_indices()` and `_indices_dirty = True` mark them stale and the
  next lookup rebuilds them in one pass. Until now a lookup after a write
  scanned the whole list, so an import, which alternates the two, was
  quadratic; `find_edge_by_id` had no index at all. The structural indices
  (by type, source, target, source+type, target+type), when clean, are
  extended in place by `add_node`/`add_edge` and stay clean; the property
  indices, which read a description an importer may set after the edge, are
  rebuilt alone. A seeded random sequence of every kind of write checks after
  each step that every index equals the one rebuilt from scratch and every
  lookup returns the linear scan's object. The helpers a GraphML export calls
  per node — `get_extractor_nodes_for_node`, `get_document_nodes_for_extractor`,
  `get_combiner_nodes_for_property`, `get_connected_nodes_by_edge_type`, the
  two `get_connected_epoch_node*_by_edge_type`, and in the exporter the
  relations string, the paradata-image attachments and the SL_PD groups —
  read the indices instead of scanning every edge, and answer in the order of
  the edge list whether the index was clean or stale (a clean index used to
  give outgoing then incoming edges, a self-loop twice). Measured on the same
  machine before and after (min of three runs; every GraphML and em.json
  written byte-identical, with `uuid4` and the hash seed fixed):

  | bench | operation | before | after |
  |---|---|---|---|
  | synthetic, 1000 US + 10 epochs (7,011 nodes) | build | 3.02 s | 0.048 s |
  | | GraphML export | 16.07 s | 1.03 s |
  | synthetic, 2000 US (14,011 nodes) | build | 11.96 s | 0.094 s |
  | | GraphML export | 67.1 s | 3.21 s |
  | Basilica Iulia GraphML (2,958 nodes, 11,577 edges) | import | 2.84 s | 0.39 s |
  | | GraphML export | 3.29 s | 0.39 s |
  | | em.json re-read | 2.17 s | 0.10 s |
  | pyArchInit demo, 51 US | import + em.json + GraphML | 0.156 s | 0.109 s |

  What is left of a GraphML export at 2000 US is quadratic in two places,
  neither touched here: the transitive reduction (networkx, 2.1 s) and the one
  `append` of the swimlane into the root document (lxml, 1.1 s).
  The test suite runs in about 5 minutes (291 s and 304 s, two runs) instead
  of 7 min 16 s.
- **A contradiction in the matrix is reported at once** (#27). When the
  temporal graph is not acyclic, `TemporalInferenceEngine.transitive_reduction`
  enumerated every simple cycle (`list(nx.simple_cycles)`) only to print the
  first: on a matrix with redundant relations — A after B, B after C and A
  after C, as pyArchInit records them — one contradiction makes that count
  grow like Fibonacci (32 US: 3 s; 40 US: minutes). It now asks networkx for
  one cycle (`find_cycle`): a 200-US chain of that shape fails in 0.15 s with
  the same message, where the previous code was still running after 20 s.
  The likeliest cause of the 990-US GraphML export that did not finish.
- **#27 · the small points**. `PyArchInitImporter.parse()` closes its
  connection on a failure too, logs the failure with its traceback instead of
  printing it to stderr, and raises `ImportError` chained to the cause.
  `importer.base_importer.redact_dsn` replaces a DSN's password with `***`
  (user, host and database stay readable), and the importer's DEBUG lines go
  through it: a `postgresql://user:password@…` no longer reaches the log
  whole. `GraphMLExporter` prints nothing on stdout: progress at DEBUG, the
  summary at INFO, a cycle at WARNING, and the Temporal Inference Report, one
  line per redundant edge, at DEBUG.

- **Templu Mare v2 · the resolver reads a dataset folder as it is** (MICRO
  Templu Mare v2, 6 October 2026). `resources.locate.resolve_graph`: a resource
  of SEVERAL files (`has_file`) has no locator of its own and was «missing»; its
  state is now its files' (`on_disk` when every file is, `files` counts them, the
  note names how many are not). `resolve`: a datablock master
  `blend://<.blend>#<Type>/<name>` is where its `.blend` is (the file looked for
  like any other; the master's digest is the .blend's); `smb://`, `afp://`,
  `nfs://` are addresses elsewhere (an archive on a NAS cited without bytes):
  `reference_only`, not `missing`.
- **Templu Mare v2 · a version that only reduces its textures is a level, not a
  copy** (D1). `check_lod_levels` said «two levels for one mesh» for every web
  version made by «Prepare for a use…» at ratio 1: same vertices and faces,
  textures at 1024 px instead of 2048. Two versions with a measured
  `texture_side_px` of different sides are no longer that warning; the same
  mesh at the same side still is, against every earlier version of the asset.
- **H1/H4 · The version for a use: ONE rule, in Python and in JS** (MICRO
  Heriverse legge lo studio, decided by E.D. 5 October 2026: nothing is
  re-exported for a viewer, the viewer reads the study and picks the version).
  `resources.versions.choose_version(entries, use, prefer_level)` is the rule,
  pure and written in prose in its docstring: the uses tried IN ORDER, the
  candidates the versions (never the master) declaring the use, the level asked
  for if one is there, else the lightest (the highest `lod_level`, then the
  fewest `size_bytes`, then the id — never the order of the neighbours); no
  version for any use → the master, SAID in a `note`.
  `resources.versions.version_for(graph, asset_or_rm_id, use, prefer_level)` and
  `api.version_for` apply it from an asset, a version or a representation model
  (its `has_linked_resource` 3D resources). The cases are
  `JSON_config/version_for_cases.json` (1.1.0, 19 cases): the same table passes
  here and in Heriverse's copy (`tests/check-version-for.mjs`, run by
  `tests/test_version_for.py` when that checkout is beside this one).
  `versions_of` entries carry `size_bytes`.
- **H4 · Two uses for a version made for a viewer, `heriverse` and `aton`**
  (node datamodel **1.6.26**, em.ttl comment of `em:use`): the package on disk
  Heriverse, or another ATON app, opens offline. `VIEWER_USES` = heriverse,
  aton, web, realtime — the order a viewer asks. The shipped mappings are
  re-stamped against 1.6.26.
- **B3 · An edge towards a node of another graph of the study is refused, in
  the CRDT and in the reader, with one sentence** (MICRO lo studio in stanza
  nomina il grafo, 5 October 2026). `crdt.edge_outside_graph` is the rule and
  the sentence («the node '…' is in the graph '…', not in this one: an edge
  joins two nodes of the same graph, and a link between graphs does not exist
  yet»); `crdt.apply_op_to_section(…, study=)` and `api.apply_op(…, study=)`
  take the container the section belongs to (a room passes it), and
  `container.parse_container` hands it to the reader, which drops such an edge
  with the same sentence. Until now the CRDT took the edge and the reader then
  dropped it. An end that is in NO graph is not this rule and stays as it was —
  the CRDT takes the edge (its node may not have arrived: the result must not
  depend on the order, `crdt-parity.json` applies the ops reversed), the reader
  drops it. The link between graphs of one study (I-4) is still to build.
  Around it, in the other repositories: StratiGraph Server refuses a
  `graph_id` the study does not have, keeps the graph in the room's log and
  names it in the replay, and lets a room be born with the study's sections;
  EMStudio brings the whole study into a room and its operations name their
  graph; EM Tools names the graph when the room holds it.
- **A1 · The alternative labels of a unit, each with its source** (MICRO le
  decisioni della sera, 5 October 2026). Quale `alternative_label`
  (em_qualia_types **1.6.7**, contextual ▸ administrative), like
  `skos:altLabel`: the first quale declared `repeatable` — one PropertyNode per
  label, its source the ordinary chain (property `has_data_provenance` →
  extractor `extracted_from` → the document that uses the label), an optional
  `data.scheme` («scavo 2013», «tesi Demetrescu»). The unit's own label
  (area.settore.tipoNumero) does not change. `s3dgraphy.labels` and
  `api.add_alternative_label / alternative_labels / remove_alternative_label /
  find_by_label` (the search finds a unit by any of its labels). The RDF
  export also says `<unit> crm:P1_is_identified_by <label>` (an E41_Appellation)
  and `skos:altLabel "…"` (`mappings.unit_predicate`); the merger keys a
  repeatable quale with its value, so a label a re-imported table adds is
  `qualia_added`, never a change of another label. Labels in nine languages;
  golden `tests/fixtures/alternative_labels.em.json`.
- **W4 · The release builds the EM site.** Step 13 of `./em.sh release … --desktop`:
  after the desktop, with its countdown, `gh workflow run build.yml -R
  zalmoxes-laran/ExtendedMatrix-site --ref main`, its jobs watched, then
  https://extendedmatrix.org/tools/emstudio/ until it links the new tag's
  installers. The site reads the newest release that is not a draft at build
  time (`src/lib/upstream.ts`), so with a draft it says so and builds nothing.

- **V1 · One vocabulary of operations on every wire.** The Sidecar and the room
  speak the same operations, `crdt.OPS` (decision of E.D.). `crdt.ops_for_local_change`
  turns a store's change (`update_node` with `fields` or `patch`, `add_node`,
  `delete_node`, `add_edge`/`delete_edge` with a nested `edge`) into wire
  operations, and `crdt.validate_op` says, in a sentence, why something is not
  one; `crdt.local_change_for_op` is the reverse door for a store that speaks
  `update_node{patch}`, keeping the op's clock; `crdt.refusal_is_news` tells a
  refusal a person must read from «the state already knew». `LOCAL_VERBS` names
  the store verbs that never travel. The cases are
  `tests/data/op_vocabulary_cases.json`, which EMStudio's twin answers too.
  Measured cause: EMtools sent the room `update_node`, refused as «unknown
  operation 'update_node'», and the Sidecar's nested `edge` reached the room
  without endpoints.

- **D1 · The level, the uses and the measures of a version** (decided by E.D.
  4 Oct 2026, `TASSONOMIA-TIER-3D.md` §2). Node datamodel **1.6.25**, `em.ttl`
  **1.6.15** (section 19). The master is `tier = master` and has no level;
  `lod0` is the first workable version made from it, `lod1…lodN` count the
  `lod_generation` steps from LOD0. The level is COMPUTED from the chain
  (`resources.versions.lod_level_of`, `lod_steps`), never held in the graph:
  written only when the graph leaves (`data.lod_level` in em.json,
  `em:lodLevel` in RDF) and at load computed again and compared
  (`check_lod_levels`): a different value, or two versions of one asset with
  the same geometry («two levels for one mesh», San Pietro's Zenodo «LOD0» =
  the case study's LOD1), is a warning. `data.use` is a LIST of `analysis |
  realtime | web | mobile_ar | print | render | preview` (`em:use`, Voyager and
  3D Tiles correspondences in the datamodel's `_note`); seven measures of a
  version (`tris_per_m2`, `texel_density_dd` in the form of the
  Demetrescu-D'Annibale formula, `texture_count`, `texture_side_px`,
  `uv_ratio`, `reduction_from_lod0`, `geometric_error_m`) with their em: terms.
  `api.add_version`: `level` optional (default: the computed one), `use`,
  `measures`; `versions_of` lists the versions of versions too and gives
  `lod_level`, `use`, `measures`, `primitives`; a version is named after its
  asset. `ResourceNode`'s docstring says why the level is still not a field.
- **R1 · One resolver for the files** (`resources.locate`, `api.resolve_files`,
  `api.resolve_file`). A resource is its identity (sha256 + node id) and a list
  of positions; the resolver tries cache → known paths (the project's standard
  tree first) → node (`on_node(hex)`, the room's HEAD) → reference and answers
  a STATE: `on_disk`, `on_node`, `both`, `reference_only`, `missing`,
  `empty_copy` (a file whose bytes are zeros). A study-relative locator
  (`/DosCo/D.32.jpg`, `//DosCo/D.33.jpg`, `DosCo\D.02.jpg`) is read against the
  project: the false «absent» of D.32 is gone (measured on the copy of San
  Pietro).
- **C1 · The standard tree of an EM project** (`project_tree`,
  `api.create_em_project`, `api.em_project_reorder_plan`): `EM/` (em.json,
  `DosCo/`, `proxies/`), `RB/`, `SB/`, `RM/`, `README.md`, `LICENCE.md`, as
  measured on E.D.'s case studies. A new project gets it; an existing one gets
  a PREVIEW of the reorder, applied only with `confirmed=True` and never over
  an existing file.
- **I1 · One list of the states and their symbols**
  (`JSON_config/em_state_symbols.json`, `datamodel.state_symbols()`): for each
  state of the resolver, the node, the room, the sync, the role and «only here»
  an id, its meaning (it/en) and the reference glyph. The symbol and its
  meaning are standard; each tool draws its own version.
- **N1 · Find a node** (`tools.node_finder`): this computer (the personal node
  :8777, the dev stack), the local network through `dns-sd` (macOS) or
  `avahi-browse` (Linux) — no new dependency, and «cannot browse» said when
  neither is there —, the saved and the typed ones; each probed (`/health`,
  `/v1/auth-config`: version, profile, ways in) and one sentence of what to do.
  EMStudio's bridge and EM Tools call the same function.
  After 1.6.0.dev35: the address is read from the TXT record too
  (`node_finder.url_of`: `scheme`, default `http`, and `path`), so the dev
  stack that `fcn-up.sh <host>` announces (`scheme=https path=/em` on Caddy's
  port) is found as `https://<host>:8443/em` and not as an `http://<host>:8443`
  that never answers; the personal node's `path=/` stays a bare address.
- **D2 · The scene's rotation is measured from the GRID north** of the CRS:
  `GeoPositionNode` writes `data.rotation_reference = "grid"` (set on load
  when a document does not carry it); the docstrings said «geographic north».

### Fixed
- **The projector finds its nodes by `node_uuid`, not by label** (#25, with
  E.D.'s diagnosis of 9 October). `_propagate_node_uuid_and_us` matched a row
  to its node by `name == str(us_table.us)`. Since 1.6 the importer names
  nodes from `node_name_template`, so the row's `'1'` never met the node's
  `'1.US1'` and no row matched; the fallback node it then built could not be
  added either, its id being already in the graph, so **every row was dropped
  in silence** and a projected graph carried no `us`, `area`, `unita_tipo` or
  `node_uuid` in `attributes` at all. The match now keys on the identity the
  importer already gave the node — the row's `node_uuid` is its `node_id` —
  and falls back to the name for graphs built outside the importer. A paradata
  row keeps its own path, which builds it a freshly typed node on purpose:
  binding it to the generic unit would alias the edges `_enrich_into` has
  already added onto a document or combiner class (Bug N). The label itself is
  unchanged and stays what it is: in Blender two nodes cannot share one, so
  across sites it also carries a site code (`TM16.1.USM100`), and a label is
  not something to parse back into columns. `strip_us_prefix` stays as the
  last resort for a graph that arrives with labels and no attributes, and now
  reads the unit type in the last dotted segment (`1.US1` → `1`,
  `TM16.1.USM100` → `100`) before falling back to the whole name, which is how
  the paradata codes are written (`D.4001` → `4001`); a name whose dot belongs
  to the value (`12.3`) is left alone rather than truncated.
  **14 of the known failures turn green** — all of
  `test_groups_export_em_template.py`, `test_update_preserves_unmapped_columns`,
  `test_sql_update_when_flag_enabled` among them — with no new failure, and
  `scripts/known-test-failures.txt` goes from 29 entries to 15.
  `test_round_trip_preserves_mapped_fields` stays, and now fails on its real
  cause: the serialiser writes `'>>'` where the column said `'copre'`. Tests in
  `tests/sync/test_projector_propagates_by_node_uuid.py`.
- **The graph's own scaffolding is not an excavated unit** (#25, pyArchInit).
  `ContinuityNode` and `GraphNode` were missing from `_NON_STRAT_TYPES`, so
  `GraphIngestor.populate_list` wrote them into `us_table` as units: a graph
  that had been through `transforms.materialize_continuity` left rows like
  `us = '_synth_BR_1'` in the archaeologists' sheets, and the node standing
  for the document left a row whose `us` was the site's own name. Neither has
  a row in `us_table`, nor an `unita_tipo` that would fit it. A round trip
  through GraphML or em.json can also hand the diamond back as a plain
  stratigraphic unit, with only `_synth_BR_<label>` left to recognise it by,
  so `_is_synthetic_node` checks the name, the node id and `attributes["us"]`
  in both loops. Tests in `tests/sync/test_ingest_skips_synthetic_nodes.py`.
- **A restored PostgreSQL dump can be written to** (#25, pyArchInit).
  `pg_restore` copies the rows with their primary keys and does not reset the
  serial sequences, so the first auto-key INSERT asks for a value the table
  already holds: `GraphIngestor.populate_list` died on
  `periodizzazione_table_pkey` while creating the epochs of a new site, and
  the whole ingest rolled back — on such a database the site could not be
  populated at all. `_resync_pg_serial_sequences` now realigns the sequences
  of `us_table` and `periodizzazione_table` to `MAX(pk)` before anything is
  written, each inside its own SAVEPOINT so a schema without one of those
  tables does not abort the transaction, and a no-op on SQLite, whose
  `AUTOINCREMENT` corrects itself. It reads no row and writes none, so
  nothing already in the table moves or is renumbered. Tests in
  `tests/sync/test_ingest_pg_sequence_resync.py`, measured against a
  PostgreSQL 17 whose periodisation rows hold the keys 1..3 with the sequence
  at 1.
- **`get_extractor_nodes_for_node` compared `edge.edge_source` with the edge
  types** (#27), so its first loop, the extractor as the source of a
  provenance edge, never matched. Fixed. The set it returns cannot change (its
  third loop found the same extractors later); a node with extractors on both
  sides now gets the sources first. No GraphML of the fixtures or of the
  benches changed.
- **The projector's groups keep their `kind`, and a SQLite projection keeps
  only its site** (#25, Enzo Cocca's report and reproduction of 7 and 9
  October). `GraphProjector` replaced `node.attributes` of the groups it builds
  — the toponym chain and the group-spec groups — instead of updating it, so
  the `kind`, `propagation` and `y_pos` the `LocationNodeGroup` constructor puts
  there for the serialisers were lost: em.json wrote the group without
  `data.kind` and reading it back failed («kind must be one of …») and degraded
  the node to `Node`. Now an update. The SQLite branch built
  `PyArchInitImporter` without `filters={"sito": sito}` (the PostgreSQL branch
  already selects `WHERE sito = :sito`), so one site of a multi-site DB brought
  the units, documents and epochs of the others: on the pyArchInit demo DB
  (ten sites), «Scavo archeologico» goes from 210 units / 342 documents / 132
  epochs to 51 / 87 / 24, the numbers Enzo measured with his patch. pyArchInit
  can drop its kind shim and its filter context manager. Tests in
  `tests/sync/test_issue25_group_kind_and_site_filter.py`.

### Changed (the release)
- **W2 · Step 7 waits for PyPI too.** Every `pip install`/`pip download` of a
  version just published (step 5's clean venv, step 7's `./em.sh rebundle`,
  dtcstamp download and `.venv` install) goes through `from_pypi`, the retry of
  steps 4 and 5, and each «not yet» says «PyPI does not show it to this pip
  yet». Measured on 4 Oct with dev34: step 7 fell at its one attempt minutes
  after step 4 had seen the version.

## [Unreleased, older part] — after 1.6.0.dev29

Everything in this section came after `069fb1a` (tag `v1.6.0.dev29`).
Needs dtcstamp **0.1.4** (the `psx://` cross-checks of
`tests/test_psx_locator.py`, which skip on an older dtcstamp, and
`stamp_identity` reading `digest_covers`).

**The decisions of E.D. on the dev29 report** (2 October 2026, MICRO le
decisioni della dev29). Datamodel: node datamodel **1.6.24**, visual rules
**1.6.31** (text only), translations 1.6 (section `packagings` added),
`em.ttl` **1.6.14** (section 18); connections and qualia unchanged.

### Added (the decisions)
- **D1 · Where a download came from** — `how.acquisition.retrieved_from`
  (a DOI as `https://doi.org/…`, or a URL) is
  `DTCAcquisitionNode.retrieved_from` in the datamodel and `em:retrievedFrom`
  in RDF (an `xsd:anyURI` for a URL), out and back.
  `dtc.acquisition_origin(node)` reads it from `data.acquisition` (an absorbed
  stamp) or `data` (bucket_acquisition's facts), and `emit_stamp` carries it
  from either. **Optional in the format**: `validate` warns «download without
  origin» for a `download` that does not say it, never an error.
- **D2 · One act = one process_id** — the 32-output test of dev29 stays the
  proof (`tests/test_dev29_one_act_n_outputs.py`); the composer's side is
  EMStudio's.
- **D4 · The digest of a set has its own term** — `em:membersDigest`
  (em.ttl, `ResourceNode.properties.members_digest`, exporter and importer)
  beside `em:checksum` + `em:digestCovers "members"`, which stay. A TTL with
  only the new term reads back as a file set. Round trip measured: San Pietro
  177/177 nodes and 328/328 edges, the RB of Segni 16/16 and 14/14.
- **D6 · A licence's name and type that disagree** — `validate` warns
  «license name and type disagree» (compared only when the name is itself a
  licence code), without rewriting the graph.
- **D7 · The Metashape reader's questions** — a chunk referenced only by the
  GPS of its cameras is placed **absolute**, with a `GCPSetNode` of
  `control: camera_positions` (each point a photograph, `accuracy_m` the
  accuracy the project records for the cameras: 10 m on San Pietro), and
  `validate` warns «georeferenced only by camera GPS»; with fewer than three
  camera positions it stays local. The digest of a master inside the project
  (`mesh.ply` in `model.zip`) is the node's `content_digest`, compared and
  never verified by downloading. Photographs whose folder is a directory
  resource of the graph — recognised by the folder's content digest
  (`resources.files.directory_for_folder`) — become its members (`has_file`,
  role `member`, relative path on the edge) instead of one resource each: on
  San Pietro the 204 Canon photographs are the night's `res:sp-canon24`, and
  the members digest of the 204 files recomputes its content digest exactly.
  The exception of `tests/test_semantic_purity.py` for the reader, and the
  name «Agisoft Metashape» without an edition, are confirmed.
- **A1** — `api.resolve_resource` answers for a DocumentNode too (its url).
- **A2** — `resources.em_id_of(name)`, the public reading of the DosCo id.
- **A3** — the packaging vocabulary in the datamodel
  (`ResourceNode.properties.packaging.values/labels`) and in the translations
  (`packagings`, nine languages, not validated); `datamodel_i18n.packaging_label`.
- **U5** — `language.confirm_recognised_language`: a recognised language,
  confirmed by a person, is written as `data.lang` only — no `ai_assisted`, no
  record. The one explicit exception to the AI marker, in the code and in the
  datamodel (`Node.properties.lang`).

### Changed (the decisions)
- **D5 · confirmed** — the block of an acquisition from 4 members, lanes named
  by their step (EMStudio), and `texturing` = projection AND baking of the
  photographs onto the mesh, one act (visual rules 1.6.31); the baking of
  levels of detail in Blender stays `lod_generation`. The «until E.D. says
  otherwise» is gone.

### Changed (the release)
- **R1 · step 0, the downstream proof** — `./em.sh release` builds the wheels
  of the working tree (and of dtcstamp with `--dtcstamp`) in
  `/tmp/em-release-<V>-prova/` and runs each consumer's tests on them in a
  temporary venv BEFORE the bump: EM-blender-tools and stratigraph-server
  (pytest), EMStudio (sync + `check:datamodel` on a scratch copy, then
  `graphml2em.py`), stratigraph-templates (`registry-snapshot` + `validate` on
  a scratch copy). A failure not in that repository's `known-test-failures.txt`
  stops it with the repository, the test and the first line of the error; a
  test red by construction until a later step (EMtools' fingerprint, rewritten
  at step 7) is said as such. It writes nothing, so `--dry-run` runs it. On
  2 Oct 2026 step 7 found EMtools red after dev29 was on PyPI.
- **R2 · a wait that reads** — the waits on publish.yml (steps 2 and 4) and on
  release.yml (step 11) print every 30 s the jobs, their state, the step in
  progress and the times, with the expected end from the last three
  successful runs; GitHub's annotations come after, as «GitHub's warnings».
  Step 4 dispatches publish.yml itself (as `./em.sh publish` did) to watch it.
  Step 11 ends with the release's URL, its assets and their sizes.
- **R3** — the workflows on Node 24 actions (checkout v5, setup-python v6,
  upload-artifact v6 — v5 is still node20, measured) and `ubuntu-24.04`.

### Fixed
- **A licence read with its name only got the type CC-BY-NC-ND** —
  `LicenseNode`'s default. Measured on San Pietro (D6): the GraphML declares
  `LICENCE:CC-BY-ND`, the em.json writes the node with its name only, and
  reading it gave it the stricter type. A licence with no type stated now
  takes its name as its type; an unnamed one none. (San Pietro's saved
  em.json keeps the type it was given: the graph is E.D.'s.)
- `resources.files.add_file` no longer gives a directory or a file set the
  implicit one-file form: the first member overwrote the digest of the whole
  (measured on the Canon folder of San Pietro).

### Added
- **The Metashape reader** — `s3dgraphy.importer.metashape_project`:
  `read_metashape_project(psx)` reads a `.psx` and its `<name>.files/` with the
  stdlib only (Metashape absent): sensors with EXIF make/model, photographs
  (enabled, aligned, dates, found on the disk or not), CRS (WKT, EPSG, kind),
  markers with their projections, the assets with their counts (faces and
  vertices from `doc.xml` and from the header of `mesh.ply`, tie points, depth
  maps) and the **operations** in order with Metashape's parameters, typed. A
  model that carries another model's BuildModel is a derived copy; with
  3DSC's `3dsc_workflow_lod0_mode=decimated` it is the LOD0
  (`lod_generation`, technique `decimation`). Nothing the project does not
  record is filled in; whatever cannot be read is a warning.
  `metashape_to_dtc(project, graph, chunk=…)` writes one acquisition per
  sensor, one act per operation (`declare_derivation`), the outputs as
  `psx:<uuid5>` masters and the placement of each mesh
  (`build_photogrammetry_delta`, `absolute` only with a CRS and ≥3 enabled
  markers). The address and the id are 3DSC for Metashape's. Measured on San
  Pietro (`sanpietro_LOD0.psx`): 273 photographs (69 + 204), 217 aligned, six
  acts, LOD0 11 656 593 faces, EPSG:7791.
- `./em.sh metashape <psx> [--chunk N] [--out file.em.json]` (and `em.bat`).
- `resources.resolver.make_psx_locator` / `parse_psx_locator`, the sixth
  `LOCATION_KIND` `psx_asset` — the twin of `blend://`, the form of
  `dtcstamp.psx_locator` (case 28). A shelf reads it as `disk`;
  `effective_tier`/`effective_packaging` read it as `master`/`datablock`.

### Changed
- `tests/test_semantic_purity.py` declares one FORMAT READER
  (`importer/metashape_project.py`) that may name the engine, with the reason
  and a test that keeps it a reader (stdlib imports only, not reached from
  `photogrammetry/`). The rule for every other module is unchanged.
- `pytest` registers the `slow` marker.

## [1.6.0.dev29] — tagged `v1.6.0.dev29` (commit 069fb1a)

Everything in this section came after `404d73b` («Bump version: 1.6.0.dev27 →
1.6.0.dev28», on PyPI 2026-10-02). Measured on the two Zenodo records of Segni
(San Pietro 7463167, Ninfeo 7463211) by the night of 1 October
(`_datasets/SegniSanPietro/_lavoro-claude/`). Datamodel at this point: node
datamodel **1.6.23**, connections 1.6.35 (unchanged), qualia 1.6.6
(unchanged), visual rules **1.6.30**, translations 1.6 (two labels added),
`em.ttl` **1.6.13**; fingerprint from `sha256:51db4ecc…93a4` (dev28) to
`sha256:027b2eead5a2b9986f83b81ff75c81aa2c27272e5539b83cb733595c956795cb`.

### Added
- **One act, N outputs**: `declare_derivation(graph, outputs=[…], inputs=[…],
  act_name=…)` writes ONE `DTCProcessNode` with a `dtc_had_output` per output;
  its id comes from `act_name` (graph-scoped) or from the sorted outputs, so
  the 32 blocks of a tiling stamp one `how.process_id` and a rerun adds
  nothing. The one-output signature and its id are unchanged.
- **The stamp of a file set**: `add_resource(packaging="file_set", files=[…])`
  writes the members digest (`dtcstamp.members_digest`) as `checksum`, with
  `digest_covers: members`; `add_file` / `remove_file` keep it current;
  `emit_stamp` emits `digest_covers: members` and `self.members` in the form
  of `dtcstamp.new_file_set_stamp` (measured: the stamp of the Segni RB passes
  `dtcstamp.verify_members` on the real files); absorbing it writes the files
  back. `resources.files.file_set_members`, `refresh_members_digest`.
- **«Not georeferenced»**: `api.georeference_state` (`undeclared` ·
  `legacy_default` · `declared`), `api.read_shift` (a SHIFT.txt such as
  `EPSG::3004 2355500 4617500 0`), `api.declare_georeference`; `validate`
  says an undeclared graph in `info` and a 4326-with-zero-shift graph in
  `warnings`, without rewriting it.
- **The EM sourcelist template**: the registered mapping `em_sourcelist_it`
  (sheet «sources», header in row 2, Nome / Descrizione / Url / Tipo);
  `api.registered_mappings`, `api.recognise_mapping`; `sheet_header` tries the
  registered mappings when none is chosen.
- **Vocabulary** (visual rules 1.6.30, proposed from San Pietro and confirmed by E.D. on 2 Oct 2026):
  `dtc_kinds.output.image_set` (glyph 09_photos) and
  `dtc_kinds.process.texturing` (glyph 03_mesh), in the nine languages.
- **RDF**: seven `em:` terms (em.ttl 1.6.13, section 17) — `em:packaging`,
  `em:tier`, `em:digestCovers`, `em:contentDigest` on a resource,
  `em:technique`, `em:parameters`, `em:software` (rdf:JSON) on a DTC step.
- `./em.sh release`: no pager in any subprocess; step 5 waits for PyPI with
  step 4's cap; the EM-blender-tools fingerprint rewritten at step 7 is the
  release's own; at the end it says whether EMStudio's release is a draft and
  prints `gh release edit <tag> --draft=false` without running it.

### Changed
- **`dtc_kind` not given stays absent** (node, stamp, re-absorption): it fell
  on `transformation` until dev28.
- **A new graph has no `epsg`** on its GeoPositionNode (it was 4326 with a zero
  shift, «WGS84 at 0,0»); `georeference_scene` refuses an undeclared graph and
  says how to declare it.
- `bucket_acquisition` recognises the acquisition every member already came
  out of (the lot of a set of stamps) instead of budding a second one.
- The TTL round trip of a DTC chain is whole: `prov:wasInformedBy` between two
  DTC events reads back as `dtc_had_input` (4 edges of San Pietro were lost),
  the seven fields above come back, a legacy `members_digest` equal to the
  checksum leaves as `digest_covers: members`; `import_rdf` no longer takes
  the graph-self node for a second graph. The `blend://` locator stays out.
- The rapporti parser is `s3dgraphy.rapporti` (re-exported by
  `s3dgraphy.sync.rapporti`): a .graphml imports without SQLAlchemy.
- A mapping's sheet is found without case; the mapped importer no longer
  prints a traceback before raising.

## [1.6.0.dev28] — 2026-10-02 (PyPI; commit 404d73b)

Everything in this section came after `83d99dc` («Bump version: 1.6.0.dev26 →
1.6.0.dev27», on PyPI 2026-10-01). Decisions of E.D. (1 Oct 2026) on the dev27
report: the four gestures of whoever exports, the language at birth in the op
(decision 12), the access mode stamped by the relay (decision 13), the local
identity of EM Tools (decision 17). Datamodel at this point: node datamodel
**1.6.22**, connections 1.6.35 (unchanged), qualia 1.6.6 (unchanged), visual
rules **1.6.29**, translations 1.6 (four labels added), `em.ttl` **1.6.12**;
fingerprint from `sha256:adf75ab9…a332` (dev27) to
`sha256:51db4eccac2e83518fa7743c0585d1022ec3b776fe0b956c29e7111e86d493a4`.

### Added
- **Four process kinds** in `dtc_kinds.process` (visual rules 1.6.29):
  `export`, `lod_generation`, `tiling`, `packing`, with labels in the nine
  languages. They reuse existing glyphs (17, 15, 00, 17) and, like every
  process kind, declare no `mapping`: a step is the crmdig:D7 of
  DTCProcessNode. EM Tools and 3DSC wrote these gestures `format_conversion` /
  `decimation` / `transformation` until now; those stamps stay true.
- **`crdt.stamp_auth(op, auth)`** (and `api.stamp_auth`): the op as a relay
  forwards it, with the access mode read from the sender's token written over
  every place an op can carry one — `op.auth`, a payload's `*_auth`, an
  `update_field` of `data.*_auth`. Returns `(op, outcome)`, outcome `stamped` ·
  `kept` · `corrected`, for the relay to count. `auth=None` removes the
  client's declaration.
- **The access mode `declared`** (`editorial.AUTH_MODES`, node datamodel
  1.6.22, `em:authMode`): an iD typed in a tool's preferences and checked by
  nobody, attested by nobody — EMStudio's declared identity, EM Tools' local
  identity.
- `crdt.is_text_node`, `crdt.op_language`, `crdt.language_fallbacks`,
  `OpResult.language` (`op` · `study_fallback` · `none`; in `as_dict` only
  when set).
- `./em.sh release <V> [--dtcstamp X] [--desktop]` (`scripts/release.py`,
  repository tooling, not in the wheel): the round dtcstamp → bump → publish →
  proof from PyPI → propagate → EMtools → StratiField's pin → the pin commits
  → push → EMStudio's desktop, each step skipped when it is already done (read
  from the repositories and PyPI, no state file), `--dry-run`, and
  `./em.sh release status`.

### Changed
- **The language a node is born in travels in the op** (decision 12).
  `make_op("add_node", …)` of a node with a text (every type but resources,
  files, translations, the graph-self, regions, shapes, positions) without
  `data.lang` raises: the producer decides it once — `und` when nobody knows —
  and every copy of a room writes the same. Measured before: the CRDT read
  the study language of the section that RECEIVED the op, so two copies with
  two study languages wrote two languages for one node. An op without
  `data.lang` is now an OLD op: the CRDT still applies it with the study
  language (the reading of `ad0bd61`), says so (`OpResult.language =
  "study_fallback"`, or `"none"`) and counts it (`language_fallbacks`). An
  invalid tag is still refused by the CRDT with its reason. The connector seam
  (`contract.connector.apply_delta`) is a producer and puts the study language
  or `und` in its ops.

### Not changed
- The pin `dtcstamp>=0.1.2` stays until dtcstamp 0.1.3 is on PyPI (the
  parent's state, the revision and the parents' hints are additive: 0.1.2
  reads them).

## [1.6.0.dev27] — 2026-10-01 (PyPI; commit 83d99dc)

Everything in this section came after `f9726af` («Bump version: 1.6.0.dev25 →
1.6.0.dev26», on PyPI 2026-10-01). Decisions of E.D. (1 Oct 2026): «il testo, la
risorsa e la selezione» (where the original text lives, `data.lang` at birth,
identical copies as addresses, the realignment with `was_revision_of`) and
«l'accesso sul campo» (one user = one ORCID; offline, the iD and a password of
the node). Datamodel at this point: node datamodel **1.6.21**, connections
**1.6.35**, qualia **1.6.6**, visual rules 1.6.28 (unchanged), translations 1.6
(unchanged), `em.ttl` **1.6.11**; fingerprint from `sha256:0be1dcff…` (dev26)
to `sha256:adf75ab96734a07e6014420c36e6a000c7e835b6c94783e66edbdfb3f940a332`.

### Added
- **`data.lang` at birth, for every writer** (rule A1): a node with free text
  born from an importer, from `api` or from the CRDT carries `data.lang`
  whenever the language is known — the source's, the declared one, or the
  study's at that moment — ALSO when it is the study's; when the study's
  language later changes, the nodes already written stay in theirs. An unknown
  language is never invented. One place: `language.birth_language`,
  `stamp_birth_language`, `stamp_born_nodes`. Writers: `declare_source_language`
  (mapping and xlsx imports), the `api` writers that create nodes
  (`place_reading`, `create_annotation_paradata`, `create_geometry_proxy`,
  `import_aton_scene`, `write_ai_draft`, `declare_derivation`), and the CRDT's
  `add_node` of a NEW node (from the section's study language; a merge never
  rewrites it). Not texts, so not stamped: graph-self, resources and their
  files, translations, annotation regions, semantic shapes, geo positions.
- **`api.realign_translation(graph, translation, text, *, by, method=None,
  review=False, ai=None, model=None, edition=None, at=None, auth=None)`**: the
  translation of the original's current text, a NEW TranslationNode
  `was_revision_of` the stale one (connections 1.6.35: the edge admits
  TranslationNode). The old one stays with author and verification, leaves no
  literal beside the original, and — having a successor — waits for nobody in
  `to_review`. In RDF the old one is an E33 with `prov:wasRevisionOf` from the
  new. `translation.successor_of`, `predecessor_of`, `is_superseded`.
- **The language of a resource's content**: on a ResourceNode `data.lang` is
  the language(s) of the FILE (one tag, or a sorted list: «latino e italiano a
  fronte» = `["it", "la"]`), not of its description; it leaves the cascade of
  the texts and goes out as `dcterms:language`, one per tag.
  `api.content_languages`, `api.set_content_languages`.
- **Where the text lives**, written in `docs/s3dgraphy_core_concepts.rst`: the
  document is the work, the resources its manifestations, the extractor the
  selection with the passage's original words in its description. Fixture
  `tests/fixtures/vitruvio/` (`build.py` writes the em.json and its round-trip and
  publish TTL): De architectura III,2,1 in Latin on an extractor, an Italian
  translation from a (fictitious) edition, an English AI one not verified.
- **Several addresses of ONE resource** (same bytes, same digest):
  `data.addresses = [{locator, residency, checked_at, ok}]`, address 0 being
  `data.url`. `api.add_address` (refuses another digest — a sister resource —
  and a resource with no digest), `api.check_address` (a dead address stays, a
  warning while a live one remains), `api.addresses`, and `api.snapshot_uri`
  (downloads the page a reference points at and gives it a dated digest,
  `checksum` + `checksum_at`; the network is opened in
  `resources/resolver.fetch_bytes`). In RDF every locator is an `rdfs:seeAlso`
  (the term the url already used) and each address `<resource>/address/<i>`
  `em:hasAddress`, with `em:locator`, `em:residency`, `em:checkedAt`,
  `em:reachable`; `em:checksumAt`.
- **How the hand of a signature had entered**: `created_auth`, `modified_auth`,
  `validated_auth` = `{mode: orcid | node_password, attested_by}` beside
  `created_by`, `modified_by`, `validated_by` (`editorial.normalize_auth`).
  `auth=` on `stamp_created`, `stamp_modified`, `verify`, `validate_ai`,
  `add_translation`, `realign_translation`; the CRDT reads an op's `auth` and
  refuses an invalid one. In RDF `<node>/auth/<stamp>` reached by
  `em:createdVia` / `em:modifiedVia` / `em:validatedVia`, with `em:authMode`
  and `em:attestedBy`.
- **`attribution`** (qualia 1.6.6): an optional `note` in its schema, the only
  field marked as natural language (`natural_language_fields: ["note"]`,
  read by `_Datamodel.natural_language_fields`).
- **`./em.sh propagate --pins`** also moves EMStudio's pin (`./em.sh s3d pin`)
  and the server's (`./bump-s3dgraphy.sh`), committing nothing; EMtools' wheels
  stay printed.

### Changed
- `declare_source_language` writes the language always (dev26: only when it
  differed from the study's) and falls back to the study's.
- `language.node_language` does not read a resource's `data.lang` (it is its
  content's language).
- `publication.promote_resource` keeps the previous locator as a second
  address when the bytes are the same (same digest before); it used to
  overwrite `data.url` and lose the disk path.
- `docs/DATAMODEL_PROPAGATION.md` step 11: `test_golden_iccd` no longer moves
  after a snapshot (templates `bdb09e4`).

### Fixed
- The verification of a node that is not AI (a translation «da rivedere»,
  then signed) did not leave in RDF: only the AI marker opened
  `_serialize_ai`. `em:validatedBy` / `em:validatedAt` now leave for every node
  that carries them, and come back.

## [1.6.0.dev26] — 2026-10-01 (PyPI; commit f9726af)

Everything in this section came after `42ea27c` («Bump version: 1.6.0.dev24 →
1.6.0.dev25», on PyPI 2026-10-01). Decisions of E.D.: the language of the data
(28 Sep 2026), the two em.ttl terms from the exporter (1 Oct 2026) and the
translations (1 Oct 2026, «Le traduzioni»). Commits: `544d21e`, `d02afc4` (the
language of the data), `68c272c`, `1991990`, `52c1978`, `f46bbba` (the
translations, the qualia, the header row). Datamodel at this point: node
datamodel **1.6.20**, connections **1.6.34**, qualia **1.6.5**, visual rules
**1.6.28**, translations 1.6 (entries added, version unchanged), `em.ttl`
**1.6.10**; fingerprint from `sha256:aab44dda…` (dev25) to
`sha256:0be1dcffb38a020e7023edb19d3764a0ff301525554755f7694c4af57945a605`
(`133a6d19…` after the language of the data, `d02afc4`; `a0b71f47…` after the
TranslationNode, `0a78197a…` after its RDF) — on purpose: every step is
datamodel.

### Added (2026-10-29 — the translations)
- **`TranslationNode`** (`TRANSL`, `crm:E33_Linguistic_Object`, node datamodel
  1.6.20): ONE translation of one text field of one node. The original stays a
  string in its field and is never overwritten; the translation carries
  `data.lang` (arrival), `data.from_lang` (departure, written because the
  original can change), `data.field` (`description` | `data.<key>`; a
  PropertyNode's value is `data.value`; never `name`), `data.text`,
  `data.method` (`manual` | `ai` | `edition`), `data.source_digest` (sha256 of
  the original, NFC + UTF-8) and `data.review_requested` («da rivedere»).
- **Edges** (connections 1.6.34): new `has_translation` / `is_translation_of`,
  any node → TranslationNode, `crm:P73_has_translation`; `has_author.source`
  += TranslationNode; `extracted_from.source` += TranslationNode, for a
  translation taken from a published edition (the DocumentNode).
- **`api.add_translation(graph, node, field, lang, text, *, by, method,
  edition=None, review=False, ai=None, model=None, from_lang=None)`**,
  `api.translations(graph, node, field=None)`, `api.text(graph, node, field,
  lang)` (`{text, lang, original, translation, reasons}`). The id is a uuid5 of
  what the translation is, so adding it twice is one node. An AI translation is
  marked `ai_assisted` like any AI-made node.
- **What waits for a person, one vocabulary**: `ai_validation.needs_review(node,
  graph)` → `ai` (unverified AI), `review_requested` (unsigned review),
  `stale` (a translation whose original changed — «da riallineare», which no
  signature clears); `api.to_review(graph)` lists them with the reasons;
  `api.verify(graph, node, author_id)` signs AI content and requested reviews
  alike (`validated_by` / `validated_at`). Named `verify`, not `validate`:
  `api.validate(graph)` is the structural check. `api.unvalidated_ai` stays.
- **The CRDT** treats a translation as a node (`add_node`, `update_field`) and
  refuses an invalid `data.from_lang` as it refuses an invalid `data.lang`;
  so does `api.set_field`.
- **RDF** (em.ttl 1.6.10, six DatatypeProperties): each aligned translation adds
  a literal on the predicate of its field with its own tag
  (`dcterms:description "…"@la` beside `"…"@it`; `crm:P90_has_value` for a
  property's value) and leaves as its own resource — `crm:P190_has_symbolic_content`,
  `crm:P72_has_language`, `prov:wasDerivedFrom` the node, `prov:wasAttributedTo`
  its author (from `has_author`), `em:sourceLanguage`, `em:translatedField`,
  `em:translationMethod`, `em:sourceDigest`, `em:reviewRequested`. An
  unverified AI translation is left out of a `publish` export (ai_validation);
  a stale one leaves no literal beside the original. `summary()` counts them.
- **`em:originalLanguage`**: a node's own `data.lang` leaves as this literal
  whenever it is declared, equal to the study's too (`Node.properties.lang`).
  The importer reads the original as the literal that is not a translation's,
  and gives `data.lang` back from it — **the D.1 limit below is closed**:
  em.json → TTL → em.json keeps `data.lang` even when it equals the study's.
- **Visual rules 1.6.28**: `node_styles.TRANSL`, the narrative's grey and
  glyph (shared, `src/2D/narrative.svg`), dashed. A mark of its own is E.D.'s.

### Changed (2026-10-29 — the doubtful qualia, measured)
- Qualia 1.6.5: `intervention_history` is marked `natural_language`; so are
  `provenance_history`, `exhibition_history`, `publication_history` and
  `ownership_chain` — `object_chain` with no schema, so their value is one
  string, marked whole. `attribution` is an `object` with separate fields (an
  actor reference, a closed list, a float) and no note: not marked.

### Added (2026-10-29 — the header row, and the language of the source)
- **`header_row`** (1-based) for `MappedXLSXImporter` and `QualiaImporter`, as
  an argument or `source_settings.header_row`; until now the header was always
  row 1 (`header=0`). Missing, it is PROPOSED (`importer/sheet_header.py`, the
  rule of EMStudio's bridge): the first row with every column of the block
  filled, kept at 1 when the mapping's own column names say row 1 is at least
  as good. `api.sheet_header(source, sheet, expected)` gives the proposal and a
  preview; `apply_mapping` / `api.mapping_apply` take `header_row` and report
  `header`. San Pietro's source list proposes row 2.
- **`source_lang`** (BCP 47), an argument or `source_settings.source_lang`:
  written as `data.lang` on the nodes an import creates, when it differs from
  the study's working language (`language.declare_source_language`);
  `apply_mapping` does it for every format and reports `source_lang_written`.

### Fixed (2026-10-29)
- `MappedXLSXImporter` read only `table_settings`, so an authored mapping (which
  says `source_settings`) had its `sheet_name` and `start_row` ignored. It reads
  `source_settings`, else `table_settings`.

### Added (2026-10-27 — the language of the data)
- **Language tags on texts, invariant names.** The datamodel marks what is text
  in a natural language: `"natural_language": true` on
  `Node.properties.description` (node datamodel 1.6.19; the base class, so every
  node type inherits it) and on the quale `narrative_content` (qualia 1.6.4).
  `name` is never marked (`US 3014`, `W5023`, `USM5023` are identities), nor is
  `inventory_number` (a code, though a string). One function answers:
  `_Datamodel.is_natural_language(node, prop)` in the RDF exporter's loader.
- **The cascade.** `RDFExporter._text_literal` builds every such literal: the
  node's `data.lang`, else the study's working language, else none. A language
  never declared leaves untagged and is counted; `data.lang: "und"` leaves as
  `@und`. Used for `dcterms:description` and the marked qualia's
  `crm:P90_has_value`; `rdfs:label` stays untagged. The narrative node still
  emits `crm:P72_has_language`.
- **The study's working language**: `GraphNode.data.language` (beside `em_id`
  and `site_position`), legacy fallback `graph.data["language"]`;
  `api.working_language` / `api.set_working_language`, and `language` in the
  study card (`study_metadata`). The exporter declares it as `dcterms:language`
  on the graph and tags the graph's description (not its name) with it.
- **BCP 47 check** (`s3dgraphy.language`): `it`, `ro`, `he`, `en-GB`, `und`. An
  invalid tag is refused where it would be written — `api.set_field("data.lang")`
  and `api.set_working_language` raise `ValueError`, `apply_op` refuses an
  `add_node` / `update_field` carrying one — and nothing is written.
- **Statistics**: `literals_tagged_node`, `literals_tagged_study`,
  `literals_untagged`, beside `definitions_label_only`; `RDFExporter.summary()`
  prints them in one line for a caller's report.
- **The importer**: a tag on a marked text gives `data.lang` back only when it
  differs from the study's `dcterms:language`, so em.json → TTL → em.json returns
  `data.lang` exactly where it was. Declared limit at that commit (D.1): a
  `data.lang` EQUAL to the study's language came back as the study's — closed
  by `em:originalLanguage` (the translations, above). Untagged literals read as
  before.

### Added (2026-10-27 — two em.ttl terms from the exporter, part H)
- **`em:derivedFromDocument`** leaves beside `P70i` when the source of
  `has_documentation` is a USD (or a series of USD): connections 1.6.33,
  `extension_when.source_node_class` — the guard may now name the source class
  as well as the target (`_Datamodel.get_extension_condition`).
- **`em:reconstructsFrom`** leaves as `<VSF> em:reconstructsFrom <SF>` when a
  SpecialFindUnit `is_part_of` a VirtualSpecialFindUnit: the new
  `mapping.inverse_extension`, read by the exporter and skipped by the importer
  (the edge comes back from P46i).
- Both leave `EM_TTL_EXCEPTIONS`, which keeps three (`hypothesizedBy`,
  `reconstructsAbsent`, `wasReusedFrom`). Registry regenerated, shipped mappings
  re-stamped.

## [1.6.0.dev25] — 2026-10-01 (PyPI; commit 42ea27c)

Everything in this section came after `312f124` («Bump version: 1.6.0.dev23 →
1.6.0.dev24»). Decisions of E.D. of 1 Oct 2026: the datamodel JSON is the
truth, so every `em:` term of `em.ttl` is cited by a datamodel or is a written
exception; dev25 goes out at once, with the fingerprint (the language of the
data waits for dev26). Datamodel at this point: node datamodel **1.6.18**,
connections **1.6.32**, qualia **1.6.3**, visual rules 1.6.27, translations 1.6,
`em.ttl` 1.6.9 (not touched); fingerprint
`sha256:aab44dda08bffbecac38e77e3049919362d4b3504b4190240a368871c3823260`.

### Added (2026-10-01 — the datamodel's fingerprint)
- **`s3dgraphy.datamodel`**, exposed as `api.datamodel_fingerprint()` /
  `api.datamodel_differences()`: one sha256 over the six datamodel JSONs a
  consumer copies (nodes, node registry, connections, visual rules, qualia,
  translations), each in **RFC 8785** canonical form, concatenated in order of
  file name — so that JavaScript computes the same digest (`em_visual_rules.json`
  holds 139 integral floats that `json.dumps` writes `1.0` and `JSON.stringify`
  `1`). Returns `{digest, versions, digests, files}`; a difference is named copy
  first (`nodes 1.6.12 vs 1.6.17`, `visual_rules 1.6.27: same version,
  different content`). `python -m s3dgraphy.datamodel [dir]` prints it.
  (`4149db5`)
- **The fingerprint per file** (MICRO em.ttl/dev25): `files` is now
  `{name: {file, digest, version}}` (was `{name: file name}`); `versions` and
  `digests` stay. `api.datamodel_fingerprint_subset(fp, names)` and
  `api.datamodel_differences(expected, found, names)` compare a consumer only
  on the files it reads, without the one digest, which covers files it does not
  read. (`066ba2f`)

### Changed (2026-10-01 — every copy compared on the fingerprint)
- **`tools/consumer_drift`** compares every datamodel a consumer holds, by
  version and by content, and names each difference; a new state, `differs`
  (same versions, different content: a copy somebody edited), fails `--check`
  like `behind` for a consumer we own and track. stratigraph-templates is a
  consumer (it reads its snapshot), compared since `066ba2f` on the four files
  its registry reads (nodes, node registry, connections, qualia): a change to
  the visual rules or the translations no longer makes it behind. (`4149db5`,
  `066ba2f`)

### Changed (2026-10-01 — the em.ttl terms in the datamodel)
- **`tests/test_em_ttl_matches_the_datamodels.py`** compares `em.ttl` with the
  datamodels whole: every `em:` term a datamodel cites is declared (`4149db5`),
  and — since `f660432` — every declared term is cited or is in
  `EM_TTL_EXCEPTIONS` with its reason (the `xfail` and `KNOWN_UNCITED` are
  gone; an exception without a reason fails).
- **30 of the 35 terms** the code wrote without any datamodel naming them are
  cited (node datamodel **1.6.18**, connections **1.6.32**, qualia **1.6.3**):
  the stamps, the tombstone, the AI marker and the verification as `properties`
  of the base `Node`; checksum / scope / residency on `ResourceNode`, checksum
  on `ResourceFileNode`; convex shapes and spheres on `SemanticShapeNode`; crs
  and `em:LocalSceneFrame` on `AnnotationRegionNode`; `em:orcidVerified` on both
  authors, `em:modelIdentifier` / `em:promptReference` on the AI author;
  `em:hasQualiaType` on `PropertyNode`; `em:propagation` on `LocationNodeGroup`;
  `em:confidenceLevel` as the declared, not emitted, alternative of the
  `confidence_level` quale; the six AP11 subproperties as `mapping.subproperty`
  of the eight physical edges; `em:inheritsQualia` as `has_property`'s
  `when_inherited`. Plain-string mapping notes: no field, no node element, no
  graph change. (`f660432`)
- **`rdf_exporter.AP11_SUBPROPS`** is built from the connections datamodel
  (`ap11_subprops()`), no longer a list of its own; the importer reads the same
  table. Nothing is emitted differently. (`f660432`)
- **Four entries corrected to what the exporter writes**: `PropertyNode.property_type`
  (`em:hasQualiaType`, was `P2_has_type`), `AuthorAINode.model` /
  `prompt_reference` (`em:modelIdentifier` / `em:promptReference`, were
  `P3_has_note`), `ResourceFileNode.checksum` (`em:checksum`, was
  `P1_is_identified_by`), and `LocationNodeGroup.propagation`, which said «not
  serialized to triplestore» although the exporter writes the non-default value
  as `em:propagation` since `c1a702c`. (`f660432`)
- Five terms of the EM theory have no edge in the graph and are exceptions:
  `hypothesizedBy`, `reconstructsAbsent`, `derivedFromDocument`,
  `reconstructsFrom`, `wasReusedFrom`. The eight shipped mappings re-stamped.

### Documentation
- `docs/DATAMODEL_PROPAGATION.md`: how a datamodel change leaves this repository
  and reaches every tool, the fingerprint, each copy checking itself, and the
  checklist; linked from `docs/SOURCE_OF_TRUTH.md`. (`1d234e9`, `2f235f0`,
  updated in `f660432` and `066ba2f`)

## [1.6.0.dev24] — 2026-09-30 (PyPI; commit 312f124)

Published on PyPI on 30 Sep 2026, 21:06 UTC (wheel sha256 `926cce4e85ea…`, as
PyPI lists it); `312f124` is the version bump, 21:06 UTC the same evening.
Everything in this section came after `fa638ef` («Bump version: 1.6.0.dev22 →
1.6.0.dev23»). Decision of E.D. of 30 Sep 2026, *la risorsa e i suoi file*.

### Changed (2026-10-22 — the one 3tz profile: 0x800 and NFC)
- **`CANONICAL_3TZ_PROFILE` / `is_canonical_3tz`** follow
  `dtcstamp/profiles/3tz.md`, the source text of the profile: general-purpose
  flags **0 on an ASCII name, `0x800` on a non-ASCII one**, and nothing else
  (criterion `flags`, was `flags_clear` = 0 everywhere, which called 3DSC's own
  archive of `Data/città.b3dm` not canonical); every name in **Unicode NFC**
  (new criterion `names_nfc`: a name in NFD, as macOS gives it, makes the same
  folder give another sha256 elsewhere). The profile keys are now
  `flag_bits_ascii`, `flag_bits_non_ascii`, `name_form`, `profile_text`.
- Two fixtures in `tests/fixtures/tiles3tz/`: `small_3dsc_nonascii.3tz`
  (canonical, written by 3DSC's module) and `small_3dsc1430128_nfd.3tz` (the
  same tree with the name in NFD, packed by the module as it was at `1430128`:
  not canonical, for that reason only).

### Fixed (2026-09-30 — the two HDT-O declarations against D7.1 final)
- **`JSON_config/hdto_extension.ttl` v0.3.** The two declarations this file
  carried against D7.1 final are corrected, both already recorded as open in
  `docs/hdto-coverage.md`:
  - **`hdto:HC9_Study`** is a subclass of **`crm:E65_Creation`** (was
    `crm:E7_Activity`). The study is the scholarly act; its documentary output
    is a separate thing joined to it by `HP25 has created`, so a report, a
    field note or a metadata record is never an HC9.
  - **`hdto:HC16_Heritage_Proposition_Set`** is a subclass of
    **`crminf:I4_Proposition_Set`** and of **`hdto:HC15_Persistent_Digital_Object`**
    (was `crm:E73_Information_Object` alone). `crm:E73` is kept so that a
    CRM-only reader still resolves the class.
  Measured on `D7.1_final.docx` (Version V1.0, Hermon et al. 2026,
  `doi.org/10.5281/zenodo.20445938`).

### Removed (2026-10-20 — the 3tz out of s3Dgraphy)
- **`write_3tz`** (module and `api`): packing a tileset is data preparation,
  and the writers are 3DSC (`cesium_exporter/archive_3tz.py`) and EMStudio
  (E.D., 30 Sep 2026). s3Dgraphy recognises (`effective_packaging`: `.3tz` →
  `archive`) and reads (`read_3tz_index`, `read_3tz_entry`, `index_is_sorted`).
- **`is_deterministic_3tz` → `is_canonical_3tz`**: whether an archive follows
  THE one profile, 3DSC's, written down in `CANONICAL_3TZ_PROFILE` (3DSC commit
  `1430128`: path order, index last and sorted, 1980-01-01 on every entry,
  stored, `create_system` 3, `external_attr` `0o100644 << 16`, no extra field,
  flags 0, no `.DS_Store`/`Thumbs.db`), criterion by criterion with the
  reasons. MEASURED: the base `TempluMare_cesium.3tz` (sha256 `232dfcbc…`,
  7302 members) is canonical; a 3tz by 3d-tiles-tools 0.5.4 is not — the time
  of writing on every entry (two conversions, two digests) and the DOS archive
  bit in the attributes (`0x81a40020`).
- The tests read three small archives written once in
  `tests/fixtures/tiles3tz/` (with 3DSC's module and with 3d-tiles-tools; the
  README says how), and the base 3tz when present.

### Changed (2026-10-20 — the kind and the glyph)
- `representations_of`: staying inside ONE kind is now written as E.D.'s
  decision (30 Sep 2026), with the example: a glb made from an image is a
  derivation of it, not a representation. Test added.
- The glyph of `FILE` (ResourceFileNode), drawn by Claude on E.D.'s decision:
  `src/2D/resource_file.svg`, declared by `node_styles.FILE.2d_file_vect`
  (em_visual_rules **1.6.27**). A node-type glyph read as a file like LINK's,
  not a DTC glyph and not a `2d_glyphs` entry.

### Changed (2026-10-20 — the revision of a resource)
- New edge **`was_revision_of` / `had_revision`**, `ResourceNode → ResourceNode`
  (connections datamodel **1.6.31**): `prov:wasRevisionOf`, CIDOC projection
  `crmdig:L21_used_as_derivation_source` (CRMdig has no term for a revision).
  The name is the one the em.json container already used for a
  `ProjectVersion` (a field of a document version, projected as
  `prov:wasRevisionOf`), now widened to resources (E.D. 2026-09-30). Label
  translated in draft in the 9 languages; the 8 shipped mappings re-stamped.
- **`replace_file` makes a new version of the resource** instead of changing
  it: a new `ResourceNode` with the same fields (not those of the old bytes nor
  the old stamps) and a derived, stable id; the same files but the replaced
  one (same roles, paths, order); the new file `dtc_derived_from` the old file;
  `new ──was_revision_of──▶ old`. The old resource stays exactly as it was,
  citable. What pointed at it does not move: the result lists it
  (`pointing_at_old`, and `old_derived_from`) and the caller decides.
- `api.revisions_of(graph, res_id)` (the chain, oldest first) and
  `api.current_revision(graph, res_id)` (the newest). A fork is a ValueError,
  not a silent pick.

### Added (2026-10-18 — the resource and its files, part 5: the tileset, for now)
- A tileset is a resource from its ROOT (`packaging: directory`, one file
  `tileset.json`, role `entry_point`, the entry point's digest) or ZIPPED
  (`packaging: archive`, one file). The EMtools Heriverse `_link` form
  (`checksum_of: entry-point`) reads that way unchanged.
- New **`s3dgraphy.resources.tiles3tz`** (pure Python, and in `api`):
  `read_3tz_index`, `read_3tz_entry` (MD5 binary search on
  `@3dtilesIndex1@`, collisions resolved by the header name, stored / deflate
  / zstd), `is_deterministic_3tz` (order, zip-epoch dates, stored, no extra
  fields, sorted index), `write_3tz` (deterministic). Specification v1.3,
  media type `application/vnd.maxar.archive.3tz+zip`.
- MEASURED on a copy of `RM/TempluMare_cesium/` (7302 files, 198 361 134 B):
  3d-tiles-tools 0.5.4 (`--ignore-scripts`: its better-sqlite3 does not build
  on Node 26) writes a 199 378 562 B 3tz in 2.1 s, stored and in order, but
  **not deterministic** — every member carries the time of writing, and two
  conversions differ in 14 606 bytes and in their digest. `write_3tz` makes
  the same-size archive, same index, same digest twice.

### Changed (2026-10-18 — the resource and its files, part 4: one way to make a resource)
- `add_resource(graph, *, name, kind, files, packaging, tier, scope,
  residency, role, derived_from, …)` is THE constructor; `add_file`,
  `remove_file`, `replace_file` change a composition. The same file in two
  resources is one `ResourceFileNode` (recognised by checksum) with two paths;
  same path and different checksum stay two. `replace_file` keeps the old file
  and declares the new one `dtc_derived_from` it. **No revision edge exists**
  for resources (measured), so the resource's earlier composition is not a
  citable node: reported, not invented.
- The **13** `ResourceNode(...)` calls in 10 modules (api.register_resource,
  publication, import_graphml, annotation/reading, dtc/residency, dtc/corpus,
  stamp/absorb ×2, shelf/core ×3, geometry/aton, geometry/proxy) now go
  through `add_resource`. Measured against `fa638ef`: the 18 resources the 12
  API-reachable points make, and the 8 the GraphML importer makes from the
  GreatTemple files, are identical. `photogrammetry/delta.py` writes a node
  PAYLOAD for the room's op log, not a node, and is left as it is. A test
  keeps any new direct constructor call out.

### Added (2026-10-18 — the resource and its files, part 3: the representations)
- `representations_of(graph, res_id)`: the resources tied by
  `dtc_derived_from`, both directions and transitively, with the `tier` /
  `packaging` a reader uses and whether they were declared. The walk stays
  inside ONE kind (`url_type`; an unstated kind does not separate): a model is
  also derived from photographs, and a photograph is not a representation of
  it — nor is another model made from the same photographs.
- `pick_representation(graph, res_id, can_open)`: the first one whose
  packaging the reader opens (the start, then nearest; `preferred` first at
  equal distance), `picked: None` and a `reason` otherwise. Nothing from an
  extension.
- EMtools graphs are recognised without being rewritten: the «internal
  resource» (`{rm}_res_blend`, `blend://`, no tier nor packaging) reads as
  master/datablock, its `promote_resource` export as distribution/file.

### Added (2026-10-18 — the resource and its files, part 2: the implicit file)
- New module **`s3dgraphy.resources.files`** (and its `api` facade):
  `resource_files(graph, res_id)` → `[{role, path, node, implicit}]`, entry
  point first. A resource with `url` and no `has_file` answers with ONE
  implicit file (a transient `ResourceFileNode`, never added: reading does not
  write); a resource with neither answers `[]`.
- Writing: `add_resource` writes the implicit form for one file (`url`,
  `checksum`, `size_bytes`, `media_type` on the resource) and file nodes for
  several — or for one with an `id`/`stamp` of its own. `add_file` moves `url`
  and `checksum` into the first `ResourceFileNode` (role `entry_point`) ONCE;
  `remove_file` back to one file brings nothing back. File ids are uuid5 of
  the checksum (the same bytes are one node) or of resource + path.

### Fixed (2026-10-18)
- em.json import: a node whose description sits only in `data.description`
  (EMStudio writes resources that way) lost it — the constructor took the empty
  top-level one and the leftover loop dropped the other. Measured on
  `Temple_20260930.em.json`: both graph resources came back with `""` (also at
  `fa638ef`). The top level still wins; `data.description` is the fallback.

### Added (2026-10-18 — the resource and its files, part 1: node, edge, packaging)
node datamodel **1.6.17**, connections **1.6.30**, em_visual_rules **1.6.26**,
em.ttl **1.6.9**.
- **`ResourceFileNode`** (`resource_file`, abbreviation FILE, `em:ResourceFile ⊂
  crmdig:D1_Digital_Object`): ONE FILE of a resource — `url`, `checksum`,
  `size_bytes`, `media_type`; for a datablock `blend_file` / `datablock` are
  read from the `blend://` locator and never stored twice. The `ResourceNode` is
  the set, the `ResourceFileNode` each member.
- **`has_file` / `is_file_of`** (ResourceNode → ResourceFileNode,
  `crm:P106_is_composed_of` + `prov:hadMember`), with `role` (`entry_point` |
  `member`) and `path` (relative to the entry point) in the edge `attributes`.
  Measured: the attributes survive em.json (schema 1); GraphML carries neither
  them nor resource nodes, and the datamodel says so.
- `dtc_derived_from` source/target += `ResourceFileNode` (a corrected texture
  declares the texture it comes from).
- `ResourceNode.PACKAGINGS` += **`file_set`** (a few files that call each
  other) and **`datablock`** (one object inside a file).
  `effective_packaging()` reads a `blend://` locator as `datablock` and a
  `.3tz` as `archive` (readings, never written).
- RDF: the file projects `rdfs:seeAlso` + `em:checksum` and reads back as a
  `ResourceFileNode`. The eight shipped mappings are re-stamped.

## [1.6.0.dev23] — 2026-09-30 (PyPI; commit fa638ef)

Published on PyPI on 30 Sep 2026, 14:13 UTC (wheel sha256 `b0fac4f15e80…`, as
PyPI lists it); `fa638ef` is the version bump, 14:12 UTC.

Everything in this section came AFTER **1.6.0.dev22 as published on PyPI**
(28 Sep 2026, 09:39 UTC). Measured, not assumed: the PyPI wheel
(`sha256 b41c974b…168a3b`, the digest PyPI lists) is byte for byte the tree of
commit `44820e1` («Bump version: 1.6.0.dev21 → 1.6.0.dev22»), and the source
now differs from it in 60 `.py` files (11 added, 49 changed, none removed) and
6 JSON configs: node datamodel 1.6.9 → **1.6.16**, connections 1.6.20 →
**1.6.29**, em_visual_rules 1.6.17 → **1.6.25**, qualia 1.6.1 → **1.6.2**,
datamodel translations 1.1 → **1.6**. The `1.6.0.dev22` EMtools bundles is a
rebuild of the source at `0573ea4`, NOT the PyPI one: same version string,
different code — hence a dev23.

### Changed (2026-10-15 — an ATON annotation with no EM node is a region on the model)
node datamodel **1.6.16**. E.D.: an ATON semantic node with no EM node of the
same name («face», «cracks») is not a stratigraphy.
- `import_aton_scene` makes it an **`AnnotationRegionNode`** of the new
  `geometry_kind` **`volume`**, named after the semantic id: it reaches the
  `"<name>_shape"` SemanticShape (`convexshapes`, `spheres`) with
  `has_semantic_shape` and the model with `is_on_resource`. ATON does not say
  which model a semanticgraph is on (measured on `ATON.scenehub.js` and the
  ten samples): `geometry.aton.model_of_scene` takes the scenegraph node
  `main` (else the only node with urls) when it loads ONE file; the
  ResourceNode with that url is reused, or a `3d_model` one is created. Two
  model nodes and no `main`, or a `main` of several files: no guess, a warning,
  the region on no resource.
- **`create_type` default is now `None`** (a region); `create_type="US"` still
  makes a unit that owns the proxy, explicitly. The report gains `regions` and
  `model`.
- With an EM node of the same name nothing changes: the shape becomes its proxy.
- New **`api.promote_region_to_proxy(graph, region_id, unit_id)`**: the shape
  becomes the unit's proxy (US → Property(geometry) → shape, the migration's
  ids — the same place an import with the unit present puts it) and the region
  **leaves the graph**, since keeping it would assert the volume twice for
  every reader of `has_semantic_shape`. A region something else points at
  (an extractor, a property) stays as a trace: it loses the shape, keeps its
  other edges, records `data.promoted_to`. A re-import after the unit appears
  does the same promotion.
- The ATON export keys a region's shape by the region's name: ATON →
  s3Dgraphy → ATON gives back the same scene (venus, skyphos), with an em.json
  or an RDF round trip in between (RDF: `P2_has_type "volume"`, no selector).
- `place_reading` refuses a `volume` (it has no vertices to place).

### Fixed (2026-10-15 — a migrated proxy's resource is a proxy_model)
`migrate_shape_urls` reused the resource EMtools' Heriverse export hangs off a
proxy's shape with the same path, but left a `3d_model` one as it was — and
`linked_proxy_resources` (with it EMtools and the Heriverse JSON) recognises
only `proxy_model`. Now the reused resource is retyped `proxy_model` whenever
the shape is a unit's proxy (the payload of a geometry property); a `3d_model`
that is no unit's proxy (a reading beyond the threshold, a shape no property
carries) stays `3d_model`. A graph already opened with the 1.6.0.dev22 EMtools
bundles (shape url gone, distribution still `3d_model`) is repaired on opening:
the one `3d_model` distribution (`tier` distribution, not `blend://`) of a
proxy shape with no `proxy_model` is retyped; the `blend://` master is never
touched, and two candidates are not guessed between. `migrate_shape_urls`
reports `retyped`. Tested on em.json files written by EMtools' own code before
21dcf93 (`tests/fixtures/emtools_proxy/`).

### Changed (2026-10-15 — a polyline comes back from Blender stitched)
node datamodel **1.6.16** (`coords.stitch_tolerance`, 1e-6 m). Measured on
Blender 5.2.0 and 5.0.1: an edges-only mesh is exported as mode 1 `LINES`,
every inner vertex twice (4 → 6); its importer ignores the document's
`extras` and makes a glTF NODE's extras custom properties; its exporter writes
custom properties to the node's `extras` with `export_extras=True`.
- `gltf_to_geometry(bytes, "polyline")` stitches consecutive `LINES` pairs
  that share a vertex (within the tolerance) into ONE ordered open chain,
  walked from the end the first segment touches. Pairs that are not one chain
  (two pieces, a branch, a loop) return `{geometry_kind, pieces, warnings}`
  and **no `coords`** — the order is not invented. New
  `geometry.gltf.stitch_lines`.
- `kind` is optional: read from the node's `extras.em_reading_kind` (the
  custom property EMtools gives a reading), else s3Dgraphy's own
  `geometry_kind`; a given kind that disagrees is used and reported in
  `warnings`.
- `geometry_to_gltf` writes `em_reading_kind` on the glTF node of a reading,
  so Blender's importer makes it a custom property by itself (verified: the
  full loop s3Dgraphy → Blender → s3Dgraphy gives back the 4 vertices in order,
  with no kind passed). Fixtures: glb exported by Blender, in
  `tests/fixtures/blender_gltf/`.

### Changed (2026-09-29 — in the source since dev22, not logged before)
- **Qualia** 1.6.2: `feature_shape` (spatial, AAT 300056273) and
  `boundary_distinctness` (material), from the DAI template (`8e6247b`).
- **Glyphs as JSON paths** (em_visual_rules 1.6.18 → 1.6.20): the authored
  SVGs in `JSON_config/src/2D` are the source of truth, `2d_glyphs` their
  generated paths (`tools.glyphs_from_svg --write / --check`,
  `tools.glyph_sheet`); author, author_ai, license, embargo and narrative
  approved (`45410b0`, `78ba92c`).
- **Chronology on demand**: `Graph.chronology()` computes bounds with their
  provenance and writes nothing; `CALCUL_*` are stripped on import and export,
  so a stale computed date never round-trips as authored data;
  `2d_file_vect`/`2d_file_rast` fixed and checked (`476e808`).
- **Narrative**: «where it is» comes from `GraphNode.data.site_position`, not
  from the 3D shift (`ecfa398`); `[[id]]` mentions a node in the prose, counted
  as a citation (`185a91d`); a block generated by AI and validated by no person
  is left out of every export and reported, `include_unvalidated=True` forces
  it in marked «⚠︎» (`a74e030`).
- **Edge labels** translated for all 56 edge types (translations 1.3,
  `edge_label(edge, lang)`) (`94b022a`).
- **CRDT**: an `add_edge` op carries the edge's declared attributes (e.g.
  `inherited`), merged commutatively (`a0ed377`).
- HDT-O coverage audit refreshed to D7.1 V1.0 (`2d8afc6`); CITATION.cff.
- The publish workflow's provenance check retries a 5xx/429 from PyPI's
  `/integrity/` endpoint (it had failed the dev22 run on a 503 while the
  attestation existed) (`57c3dc7`).

### Added (2026-10-11 — convex hulls and spheres of ATON and Hathor)
`geometry.aton` (also `api.import_aton_scene` / `api.export_aton_scene`). The
format was measured on ATON's own code: `scene.semanticgraph.nodes[<id>]`
holds `convexshapes` (one flat `[x,y,z, …]` list per hull) and `spheres`
(`[x, y, z, r]`), in three.js Y-up coordinates under the semantic root (the
scenegraph transforms do not apply); `semanticgraph.edges` is
`{parent: [children]}` with root `"."`.
- Import: each semantic node becomes the proxy of the EM node of the same name
  — shape `"<name>_shape"`, the Heriverse rule; US → Property(geometry) → shape
  through `migrate_legacy_proxies` — created as `create_type` (default `US`)
  when missing, and listed in the report. A `toYup` node is rotated to Y-up
  once. Hulls and spheres stay in the shape's data, no resource.
- Export: the hulls and spheres of every proxy, keyed by the unit's name,
  written into a copy of the scene (only `convexshapes` / `spheres` rewritten).
- Tested on ATON's venus and skyphos samples (`tests/fixtures/aton/`):
  ATON → s3Dgraphy → ATON gives back the same scene, with an em.json round trip
  in between.

### Changed (2026-10-11 — the geometry of whoever argues lives in the node)
node datamodel **1.6.15**, connections datamodel **1.6.29**, CRMem (em.ttl)
**1.6.8**. Geometry is divided by ORIGIN, not by shape (E.D., 30 Sep): the point
of a reading, the line and the polyline of a measure are data of the node.
- `AnnotationRegionNode` point / line / polyline carry `data.coords`
  (`[[x, y, z], …]`, scene-local glTF frame, metres) with `crs` and, for a line
  or a polyline, `length` (computed from the coords) and `unit`.
  `place_reading` writes no glb and no SemanticShape; `api.measure` reads the
  coords.
- The threshold is data: `coords.inline_max_vertices` = 500 in the node
  datamodel. Above it the vertices go to `readings/<id>.glb`, a `3d_model`
  resource the region reaches with `has_linked_resource` (new source in
  connections 1.6.29), with a warning.
- Migration on opening: a region reaching `readings/<id>.glb` through a
  SemanticShape (2026-10-06) gets its coords from the file; the shape and its
  edge leave, the file stays. Without the folder or the file the old form stays
  and a warning says so.
- RDF: `<region> geo:hasGeometry <region>/geometry`, `geo:asWKT "<CRS IRI>
  POINT Z | MULTIPOINT Z | LINESTRING Z (…)"^^geo:wktLiteral` (GeoSPARQL 1.1).
  `em:LocalSceneFrame` is the IRI of the scene frame, the OGC EPSG IRI of a
  projected one. The round trip stays isomorphic.
- `geometry.gltf` (also `api.geometry_to_gltf` / `api.gltf_to_geometry`):
  `geometry_to_gltf(node) -> bytes`, `gltf_to_geometry(bytes, kind) -> dict`.
  POINTS, LINE_STRIP, and TRIANGLES for a SemanticShape's convex hulls
  (hull triangulated here); spheres travel in the glTF `extras`.

### Changed (2026-10-11 — the proxy reaches its glb through a resource)
connections datamodel **1.6.28**. The proxy is a property of the US and its
`.glb` is a `proxy_model` **resource** (E.D., 30 Sep): the SemanticShape
reaches it with `has_linked_resource` → `ResourceNode(url_type proxy_model)`,
the hinge a Representation Model uses for its bytes (P67). `SemanticShapeNode`
joins the sources of `has_linked_resource`.
- `create_geometry_proxy` writes the resource (`proxy_resource_id`, uuid5 of the
  shape), never the shape's `url`; hulls and spheres stay in the shape's data.
- `SemanticShape.url` is read and not written: on opening an em.json,
  `geometry.migrate.migrate_shape_urls` turns a leftover `url` into the
  resource (idempotent), after `migrate_legacy_proxies` — so EMtools' older
  `US → has_semantic_shape → '<US>_shape'(url proxies/<US>.glb)` is covered. A
  resource EMtools' Heriverse export already hangs off the shape with the same
  path is reused (typed `proxy_model` if it said nothing 3D), never doubled.
- `store_backed_geometry` binds a resident proxy to its property **and unit**.
- The Heriverse JSON projects the resource's path back on
  `semantic_shapes[id].data.url`, where Heriverse.js looks for it.
- The eight shipped mappings re-stamped against connections 1.6.28.

### Changed (2026-10-11 — the eight DTC glyphs approved)
em_visual_rules **1.6.25**. E.D. approved the eight drafts of 1.6.23: they
moved to `src/2D/dtc/<glyph>.svg`, the word BOZZA removed, and their
`2d_glyphs` entries no longer carry `"draft": true`. The four recoveries
(download, local_import, uri_reference, ingest) still have no glyph.

### Changed (2026-09-30 — the capture in RDF)
em_visual_rules **1.6.24**, node datamodel **1.6.14**, CRMem (em.ttl) **1.6.7**.
A capture is not a transfer: a `DTCAcquisitionNode` now takes the RDF class its
kind declares in `dtc_kinds.acquisition.<kind>.mapping`, instead of
`crmdig:D12_Data_Transfer_Event`:
- photo, laserscanner → `crmdig:D2_Digitization_Process` (⊂ D11 ⊂ D7);
- topographic, gnss_survey → `crmdig:D11_Digital_Measurement_Event` (⊂ D7);
- field_drawing, recording_sheet → `crm:E65_Creation` (⊂ E7) — made by hand,
  the file is their copy: no machine event is asserted;
- the retrievals (download, local_import, uri_reference, ingest) stay D12.
`utils.get_dtc_kind_mapping` reads the rule; the RDF importer reads the same
table back, and counts the kind's superclasses as redundant (E65's
`crm:E7_Activity` is ActivityNodeGroup's class: without it the reading depended
on the order of the types). The round trip stays isomorphic.

### Added (2026-09-30 — the eight DTC glyphs, as drafts)
em_visual_rules **1.6.23**. The eight kinds 1.6.22 left without a glyph —
gnss_survey, field_drawing, recording_sheet, decimation, georeferencing,
format_conversion, classification, vectorization — name a pictogram (12…19),
drawn on the 2017 DTC family and marked BOZZA. They live in
`src/2D/bozze/dtc_<glyph>.svg`, so their `2d_glyphs` entries carry
`"draft": true`. **Approval is E.D.'s**: move the file to
`src/2D/dtc/<glyph>.svg`, remove the word BOZZA, rerun
`glyphs_from_svg --write`. `test_visual_assets` accepts a DTC draft (a node-type
glyph still may not be one).

### Changed (2026-09-30 — USR / USS are a coating US)
The genres of a US are a vocabulary written in the datamodel (E.D.): node
datamodel **1.6.13**, datamodel translations **1.6**.
- `stratigraphic_kind` gains **`coating`** — plaster, floors, revetments: the
  USR (*rivestimento*) and its English translation USS (*surface*), the same
  thing in two languages. The enum now carries `labels`, `codes` and
  `default_code` per kind; the labels are translated (section
  `stratigraphic_kinds`, `stratigraphic_kind_label()`: «muraria», «di
  rivestimento»).
- New node element **`source_code`** (em.json `data.source_code`): the code a
  unit came in with when it is not its kind's default (USS, WSU…), so the way
  back to pyArchInit gives the same code. A USR or a USM writes nothing.
- Recognised like the USM: from the NAME (GraphML, and now also an xlsx row
  typed `US`), from the TYPE string (xlsx `TYPE`, pyArchInit `unita_tipo`), and
  a legacy em.json with `node_type "USR"` / `"USS"` opens as US + coating.
- **Fixed**: the pyArchInit SQLite importer read the unit type only from the
  mapping (`US`), never from the row's `unita_tipo`: a USM row came in as a
  plain US. It now reads the row.
- `yed_classifier` separates the two: USM → `US_MASONRY`, USR / USS → the new
  `US_COATING` (before, all three were masonry and reached pyArchInit as
  `unita_tipo = "USM"`, with the prefix left in `us`). `strip_us_prefix` and
  `UNITA_TIPO_CANONICAL` know USR / USS (USS → USR).

### Changed (2026-09-30 — USM is a masonry US)
USM is a recording practice, not a category of the EM language (E.D.): a masonry
unit is a **US with `data.stratigraphic_kind = "masonry"`**, and its name keeps
saying USM. Node datamodel **1.6.12**.
- `StratigraphicUnit.stratigraphic_kind` — a node element like `definition`
  (em.json `data.stratigraphic_kind`), absent on an ordinary US; not projected to
  RDF yet (the fitting term, CRMba B5, is not adopted).
- **Read migration**: an em.json with `node_type "USM"` — never a type of the
  datamodel, it opened as an untyped node — opens as US + masonry
  (`_LEGACY_NODE_TYPE_MIGRATIONS`, next to the `link → resource` alias).
- **GraphML import** recognises a USM from its NAME (`USM101`, `USM 3`, and
  pyArchInit's localized WSU / MSE / UEM / USZ / ΤΣΜ): the EM palette draws a USM
  exactly as a US, so the name is all a yEd file carries. Export is unchanged —
  same shape, same name — so yEd → em.json → yEd is stable.
- The type string `USM` (xlsx, pyArchInit `unita_tipo`) now builds a US +
  masonry instead of a base `StratigraphicNode`; a masonry US goes back to
  pyArchInit as `unita_tipo = "USM"`.

### Changed (2026-09-30 — the capture is an acquisition)
em_visual_rules **1.6.22**; datamodel translations **1.5**.
- The `acquisition` axis of `dtc_kinds` has two families, stated per kind as
  `family`: **capture** (photo, laserscanner, topographic — moved from `input`
  with the same keys — plus gnss_survey, field_drawing, recording_sheet) and
  **retrieval** (download, local_import, uri_reference, ingest). No new node type:
  `DTCAcquisitionNode` accepts a capture. `input` keeps no entries and is a read
  alias of the capture family (`get_dtc_kinds()["input"]`);
  `get_dtc_kind_family(kind)` reads the family.
- `process` gains decimation, georeferencing, format_conversion, classification,
  vectorization. The new kinds have no glyph yet.
- **The stamp's definitive form is `how.dtc_kind = <capture>`.** EMStudio's
  provisional form (`local_import` + `how.acquisition.capture`, or
  `data.capture` on the node) is still read — by the absorber, the emitter and
  the em.json reader — and a stated retrieval other than the placeholder
  `local_import` is never overwritten (`dtc/capture.py`).
- **Fixed**: an origin stamp absorbed back became a `DTCProcessNode`
  «transformation», losing its kind and its facts, and re-absorbing the same
  stamp disagreed with itself. It now comes back as a `DTCAcquisitionNode`.
- `datamodel_i18n` has a `dtc_kinds` section (every kind's label, all nine
  languages as drafts) and `dtc_kind_label(kind, lang)`.

### Fixed (2026-10-07 — removing an edge removes it from the indices)
`Graph.remove_edge` and `Graph.remove_node` rebuilt their lists but left the
indices clean: once built, the queries by source, target and type still saw the
removed edge, and `find_node_by_id` / `get_nodes_by_type` the removed node.
- `Graph.nodes` / `Graph.edges` are now properties whose setter marks the
  indices stale — this covers `remove_*` and every module that removes by
  assigning a filtered list (rights, importers, projectors).
- `refine_edge_types` marks them stale when it retypes an edge;
  `invalidate_indices()` is the public way to say it after an in-place
  mutation (used by the ingestor's promotion, the projector, the paradata
  store).
- `place_reading` no longer sets `_indices_dirty` by hand.
- The CRDT tombstone works on em.json dicts, not on a `Graph`: no index there.

### Added (2026-10-07 — the place of a reading in RDF: the quote and the measure)
The two fields 1.6.10 left unprojected now travel, and come back.
- A passage's **quote**: `oa:hasSelector` → `oa:TextQuoteSelector` with
  `oa:exact`, at `<region>/quote`. W3C Web Annotation is reused because the
  quote has no fragment-string form and no other standard term; the offsets
  stay the RFC 5147 `em:hasSelector "char=s,e"` (not also a
  TextPositionSelector — that would be a second copy).
- A line's / polyline's **length**: `crm:P43_has_dimension` →
  `crm:E54_Dimension` at `<region>/length` (`P2_has_type "length"`,
  `P90_has_value` xsd:double, `P91_has_unit` → QUDT unit IRI for m/cm/mm/km,
  else `s3d:unit_<u>`, and `em:crs` for the frame). CIDOC already has the
  shape; a literal would hide the number from every CRM reader.
- `em:vertexCount` on the 3D kinds. The glb stays a linked resource: its URL is
  the SemanticShape's `rdfs:seeAlso`; no coordinate enters RDF.
- em.ttl 1.6.6 (`em:vertexCount`, `em:crs`, `oa:` prefix); node datamodel
  1.6.11 (mapping text of AnnotationRegionNode only); 8 mappings re-stamped.

### Changed (2026-10-06 — the place of a reading, part 3: `data.geometry` migrates)
An extractor's legacy `data.geometry` (EMStudio from 2026-10-05:
`{kind:"passage", start, end, text}` or `{kind:"point3d", p, on}`) becomes, on
opening, a place node it `extracted_from` (`annotation.migrate_reading`, run
by `parse_emjson` / `parse_container`). The field is read, never written
again. A point needs a folder for its glb: `load_emjson_file` /
`load_container_file` pass the file's folder (`project_root`); a dict opened
in memory keeps the field (the only copy of the coordinates), warns, and the
next open from a file completes it. `on` is resolved by id, then by the name
of a model/document (kept as `on_mesh` on the place), then the one document
the extractor reads. A region of another kind already read shadows the field
(left alone, reported); an unknown kind is left alone and said.

### Added (2026-10-06 — the place of a reading, part 2: the glb)
- `s3dgraphy.geometry.reading_glb`: `write_glb` / `read_glb` (and
  `glb_bytes` / `parse_glb`), by hand, no dependency: one float32 VEC3
  accessor, glTF mode 0 POINTS (point), 1 LINES (line), 3 LINE_STRIP
  (polyline, open). Coordinates verbatim, in the model's glTF frame (Y-up,
  scene-local, metres) — the proxies' frame. Checked: Blender 5.1 imports the
  three as loose vertices, one edge, an open chain.
- `place_reading` for the 3D kinds: region `─has_semantic_shape→`
  SemanticShape(`type="generic"`, `url="readings/<region id>.glb"`), the file
  written under `project_root` beside `proxies/`; without a root the nodes
  are made and the result warns the file was not written
  (`write_reading_glb`).
- `api.measure(…, project_root=…)` re-reads the glb and reports whether it
  agrees with the node's cached vertex_count/length (`glb.agrees`).

### Added (2026-10-06 — the place of a reading, part 1: the node)
E.D. 2026-09-29: the place a reading looked at is ONE node,
`AnnotationRegionNode`, with a new `geometry_kind`: `region2d` (default — every
older region), `passage` (`start`, `end`, `text`; selector `char=s,e`),
`point`, `line`, `polyline` (coordinates in a `.glb`, never in the node, which
keeps `vertex_count` and, for line/polyline, `length` + `unit` + `crs`).
- `api.place_reading(graph, extractor_id, on_id, geometry)` fixes the place:
  `extractor ─extracted_from→ region ─is_on_resource→ on`; placing it again
  moves the reading (the old `extracted_from` goes, the old region stays).
- `api.measure(graph, region_id)` → `{length, unit, crs, value}`; `value`
  (`"1.234 m"`) is what «Usa come valore» writes.
- Node datamodel 1.6.10; connections 1.6.27: `is_on_resource.target` += the
  three representation models (a 3D reading sits on a model). The `.glb` is
  reached with `has_semantic_shape`, the proxy's hinge: no new edge.
- RDF: `P2_has_type` carries `geometry_kind` for the new kinds, a passage its
  `char=` selector. The quote and the measure are not projected yet.
- The 8 shipped mappings re-stamped against the new datamodels.

### Added (2026-10-05 — the stamp writes and reads its title and description)
dtcstamp 46b3b78 gave the stamp an optional `self.label` (title) and
`self.description`, outside `substance`. Now s3Dgraphy uses them:
- `stamp.emit` writes `self.label` from the resource's `name` (omitted when it
  repeats the id or the digest) and `self.description` from its description.
- `stamp.absorb` brings them to the node the stamp feeds as a **marked copy**
  (`data["copied_from_stamp"] = ["name", "description"]`), never over a name
  or description a person wrote; a later stamp may update a copy. Also on a
  deduplicated absorb (the words are not substance), never on a dry run.
  `AbsorbResult.courtesy` lists the fields copied.
- The shelf keeps the receipt in dtcstamp's one form: `shelf.shelve_stamp` /
  `api.shelve_stamp` store `dtcstamp.receipt(stamp)` on
  `data["stamp_receipt"]`, and `_entry` reports it as `receipt`.
A stamp without title and description stays valid all the way.

### Changed (2026-10-05 — the `SOURCE_i` column in the xlsx)
E.D. 2026-09-29: the Claims sheet's `DOCUMENT_1` / `DOCUMENT_2` become the
generic **`SOURCE_1` / `SOURCE_2`**: the id of a document or of a
stratigraphic unit, the kind resolved from the id (a document first). The
extractor is named `<source>.<nn>` either way. `DOCUMENT_i` stays valid for
the sheets already written: the importer (and `api.write_em_data`) reads it
as `SOURCE_i` without the drift warning; a sheet carrying both keeps
`SOURCE_i` and fills its blanks from `DOCUMENT_i`, a disagreement is a
warning. The exporter, `UnifiedXLSXImporter._COLUMNS`, the StratiMiner
prompt, `em_data_template.xlsx` and the importer docs write `SOURCE_i`. An
unresolved id is a warning (`unknown SOURCE …`), as an unknown document was.
An annotation region is a legitimate source in the graph but has no sheet in
the workbook, so its id does not resolve from a workbook alone.

### Changed (2026-10-05 — the RDF round trip stays complete)
E.D. 2026-09-29: the round trip is a technical transformation, not a
publication. `RDFExporter(mode="round_trip")` (the default, and
`api.project_ttl` / `api.container_to_ttl`) no longer leaves out AI-made nodes
no person verified: they travel with their `ai_assisted` marker, unflagged,
and come back unvalidated (ttl → graph → ttl isomorphic). Only
`mode="publish"` leaves them out, and with `include_unvalidated=True` carries
them marked «⚠︎»; `include_unvalidated=True` with `round_trip` is now a
`ValueError`. `api.container_to_ttl` gains `mode` and `include_unvalidated`.
The other exits towards others (html, docx, LaTeX, ipynb, xlsx) are unchanged:
they exclude by default.

### Changed (2026-10-04 — two English phrases)
Connections datamodel **1.6.26**: `combines.ui_phrase.as_source` «{node}
combining {x}» → «{node} of {x}» («Combiner of D.3.1»; the other languages
already read «di/de/von»). `has_property.ui_phrase.as_source` «{node} with
{x}» checked for every owner the edge admits (unit, document, RMDoc, epoch,
graph) and kept. `datamodel_translations.json` **1.4** (the English of that
phrase).

### Added (2026-10-04 — AI support and its verification, on nodes)
Connections datamodel **1.6.25** (E.D. 2026-09-29): an AI proposal a person
accepts stays signed by the person, with the mark «supporto AI», and stays
among the warnings until a person verifies it with their ORCID. The narrative
blocks already did this; now nodes do, with the same names, in `data`. See
`validated_by.node_verification_note`; no edge changed.

- `s3dgraphy.ai_validation`: `data.ai_assisted = {model, by, prompt_ref,
  fields?}` (`by` = the AuthorAINode; no `fields` = the whole node);
  `data.validated_by` (a human AuthorNode with a well-formed ORCID) and
  `data.validated_at`. `mark_ai_assisted` (clears a previous verification),
  `validate_node`, `unvalidated_ai`, `export_view`. The block's word
  `ai_generated` is read on a node as an alias.
- `api.unvalidated_ai`, `api.mark_ai_assisted`, `api.validate_ai`.
- Exports: xlsx (`UnifiedXLSXExporter(..., include_unvalidated=False)`), RDF
  (`RDFExporter(..., include_unvalidated=False)`, both modes; `project_ttl`)
  and html/docx (through `bake_narrative`: `excluded_nodes`, `pending_nodes`)
  leave out unvalidated AI nodes by default — a whole node with its edges, or
  the listed fields emptied. Forced, each touched text field starts with «⚠︎».
  em.json is the record and is never filtered.
- RDF carries the marker as `em:aiAssistedBy` / `em:aiModel` /
  `em:aiPromptRef` / `em:aiAssistedField` and the verification as
  `em:validatedBy` (domain widened to crm:E1) / `em:validatedAt`, all declared
  in `em.ttl`; the importer reads them back into `data` and takes «⚠︎» off
  the text, so a forced round trip is isomorphic. A forced xlsx read back
  keeps the node AI-assisted and unverified instead of laundering it.
- Narrative `Block` gains `validated_at` (set by `endorse`).
- The CRDT merges `ai_assisted`, `validated_by`, `validated_at` as content,
  like every `data.*` field (none is in `META_KEYS`).

### Changed (2026-10-04 — an extractor may read from a unit)
Connections datamodel **1.6.24** (E.D. 2026-09-29, extending the proposal of
2026-09-28 on SF/RSF): `extracted_from.target` += `StratigraphicNode`, the
whole family by class (US, USV/s, USV/n, SF, RSF, VSF, USD, serSU, USN…). An
extractor may read from a unit that itself has the property it feeds. See
`extracted_from.unit_source_note`.

- `api.validate` gains `info`, suggestions that do not touch `ok`: an
  extractor reading from a unit with no property of the name it feeds
  (`diagnostics.extraction_source_hints`, direct or through a combiner).
- xlsx: `DOCUMENT_i` may name a `Units.ID`; the exporter writes a unit source
  that way and the importer resolves it, naming the extractor
  `<unit>.<nn>` as it names `<document>.<nn>`.
- The Aiano case (extractor `SF04.2` → `SF04`) is no longer «outside the EM
  language»: its degraded edge now has one reading, `extracted_from`. Two tests
  that pinned the old refusal moved to a pair that still has none
  (extractor → property).

### Added (2026-10-04 — a property with more than one owner)
Connections datamodel **1.6.23** (E.D., revisione della scrivania v7): a
PropertyNode may have more than one incoming `has_property`. A unit
*instantiates* another's property — a USV/s takes the `material` of the US it
completes — and the property stays one, with one value and one chain. The
inheritance is declared, never automatic: the inheriting edge carries
`attributes["inherited"] = True`. The property stays in its original owner's
ParadataNodeGroup; see `has_property.owners_note`.

- `s3dgraphy.ownership`: `inherit_property`, `original_owner` (the unmarked
  edge, else the paradata group, else the earliest `created_at`, else not
  stated), `property_owners`, `shared_properties`; the same three in `api`.
- xlsx: an inheriting owner is a Claims row with `TARGET2_ID` = the original
  owner and a copy of the value; the importer links it to the original's
  property instead of minting a second one (it used to split the property in
  two). A row whose original cannot be found warns and stays a claim.
- RDF: the inheriting `has_property` also goes out as `em:inheritsQualia`
  (`rdfs:subPropertyOf em:hasQualia`, declared in `em.ttl`); the importer puts
  the mark back on the edge.
- Merge: replacing one owner's qualia (`_remove_qualia_subtree`) no longer
  deletes a property that another owner still has; only that owner's edge goes.
- GraphML patcher places a shared property beside its original owner.

### Added (2026-10-02 — the edges learn to speak)
Connections datamodel **1.6.22**: `edge_types.<edge>.ui_phrase` =
`{as_source, as_target}`, the phrase a menu uses to create a node linked by
that edge («{node} above {x}», «{node} of {x}», «{node} for {x}»), on the 34
edge types EMStudio's menus can propose (measured). `{node}` is the new node's
type label, `{x}` the existing node's name; `as_source` when the new node is the
edge's source. EM language, so it lives here, not in a consumer's i18n.

- `datamodel_translations.json` 1.2: new section `edge_types`, fields
  `ui_phrase_as_source` / `ui_phrase_as_target`, drafted in all nine languages
  (`validated_<lang>: false`). `datamodel_i18n.edge_ui_phrase(edge, direction,
  lang)` reads it with the English fallback; `seed`, `--check`, `stats` and the
  xlsx cover it.
- `tests/test_edge_ui_phrases.py`: both placeholders in every language, keys
  that point to existing edges, the measured menu set covered.

### Added (2026-10-02 — the document is drawn from paths)
`em_visual_rules` **1.6.21**: `2d_glyphs.document`, generated from
`src/2D/document.svg`, and `2d_render_glyph_types.aspect.document` = 0.636
(the drawing and the yEd palette node; EMStudio's 0.78 measured its own
hand-drawn sheet). New role `border` (restyled from `document_variant_styles`,
never by a theme) and new list `2d_render_glyph_types.sheet_types`: the
document has paths but its label sits on the sheet, so it is not in `types`.
`document.svg` redrawn without changing a pixel so its outline is a stroke.

### Changed (2026-09-28 — an epoch's properties are its own; sub-epochs from `PARENT`)
Connections datamodel **1.6.21**: `has_property.source` += `EpochNode`,
`GraphNode` (E.D., revising 1.6.1). Every node that accepts properties
receives them directly; the ParadataNodeGroup is a grouping on top, not a
passage.

- `UnifiedXLSXImporter`: a claim whose `TARGET_ID` is an epoch
  (`absolute_time_start`, …) now lands as `EpochNode —has_property→
  PropertyNode` with its full paradata chain. It used to degrade silently to
  `generic_connection`: 29 edges on StratiMiner BM01 v6.2, 39 on BM03 → 0.
  No ParadataNodeGroup is created.
- `Epochs.PARENT` (optional; aliases `PARENT_ID`, `PARENT_EPOCH`) →
  `has_sub_epoch` PARENT → epoch. An assertion, never inferred from
  START/END; unknown PARENT, self-reference and cycles warn and write nothing.
  Described in `StratiMiner_Extraction_Prompt.md` (Sheet 2).
- `api.validate` reports, under `issues`, a PropertyNode that sits in X's
  ParadataNodeGroup without `X —has_property→` it
  (`diagnostics.paradata_group_incoherences`).

## [1.6.0.dev22] — 2026-09-28 (PyPI; commit 44820e1)

Everything below was already in the 1.6.0.dev22 wheel on PyPI.

### Added (2026-09-20 — FMPXML, a FileMaker export read as the table it is)
`format_type: "fmpxml"` joins `sqlite`/`xlsx`/`csv`/`xml`, for the
`FMPXMLRESULT` shape DANA (Israel Antiquities Authority) and many other
excavation databases produce. XML syntax, table shape: field names declared
once in `METADATA`, values matched to them BY POSITION in `RESULTSET/ROW/COL/
DATA`.

A format of its own and not a flavour of `xml`, because the plain XML reader
does **not fail** on one of these — it finds the same path repeated N times per
record, cannot tell one field from another, and produces rows whose columns
collide. Silent, and it looks like data.

- `FMPXMLImporter` inherits from `XMLImporter` and overrides one thing: how a
  record becomes a dict. Everything downstream — `column_mappings`, relations,
  filters, the base importer — is unchanged, so a FileMaker source behaves like
  any other table.
- `sniff_format(path)` reads the root element of an existing `.xml` and returns
  `fmpxml` when it is one. `detect_format` still goes by extension alone and
  opens nothing.
- `mapping_source_fields` returns `declared_rows` (`RESULTSET/@FOUND`) beside
  `read_rows`. They differ only on a truncated file, and a truncated import that
  reports success is the failure nobody notices until much later.
- Declaring `record_path` or `table_name` on a `fmpxml` source is a warning:
  one table per file, nothing to select inside it.

**Chosen over a converter on purpose.** A script writing CSVs beside the source
would work and would leave a second copy of every dataset on disk — the wrong
default for an excavation database under a partner's licence. A mapping that
reads the export where it lies copies nothing.

**Measured on the Yavneh Area M4 export** (Israel Antiquities Authority, DANA):
173 loci in, 976 nodes, 803 edges, no warnings. And one thing found only by
looking at the values: `d_locus_no` in `loci.xml` is always numeric (`35005`)
while the column of that NAME in `stratigraphy.xml` carries the prefixed form
(`W35005`, `#35009`, `W35050 [W35011]`). Same name, two files, two contents.
Using the numeric form as identity loses 47 of the 161 loci the relations refer
to; `d_locus_no_canonical` loses none. It is now in the schema documentation,
because it is a trap any FileMaker export can set.

### Added (2026-09-19 — IMPMAP, attaching a table to a graph that is already right)
Loading a legacy dataset has **two modes**, and only one of them was reachable
from `mapping_apply`: the table brings the stratigraphy (relations in the
columns, the graph born out of the dataset), or **the graph brings the
stratigraphy and the table brings the rest** — no relation columns anywhere, a
sequence drawn by hand, and a spreadsheet that goes on being edited elsewhere and
re-read. The second is by far the more common, and it was the dangerous one.

- **`unmatched` / `unmatched_count` in the `apply_mapping` report.** In
  `enrich_only` a row whose key matches no node is SKIPPED — right — but it was
  skipped into a per-row warning and nothing else. Measured before this round: a
  host graph of 620 nodes enriched from a csv holding one typo (`su = 99999`) →
  **624 nodes, `99999` created, zero warnings**; with `enrich_only` reachable but
  silent, the damage simply moves from "a typo invents a unit" to "a typo loses a
  row", which is harder to see. `BaseImporter.unmatched` collects the keys that
  found nothing, in reading order, each once — one attribute, filled by the same
  branch in `base_importer` that all four importers reach, plus the
  pyArchInit importer's own copy of that branch (which keeps its richer
  `orphans` beside it). Empty unless `enrich_only`: everywhere else an unknown
  key legitimately creates its node, and "unmatched" would name every row.
- The not-ok returns carry the two keys as well, so a caller reads the report's
  shape once.
- Stated because the second mode rests on it, and verified rather than assumed: a
  descriptor with **no `relations` at all** is a valid mapping.
  `mapping_validate` asks for an `is_id` — the join key — and nothing more. No
  schema change was needed.

### Fixed (2026-09-19 — REV1, the reverse of a relation is the same relation)
The connections datamodel has declared the inverses since 1.5.3 (`overlies` ⇄
`is_overlain_by`, `cuts` ⇄ `is_cut_by`, `fills`, `abuts`, `is_after` ⇄
`is_before`, ~45 more) and `connections_loader` expands them correctly. **Two
places did not read that expansion**, independently, and neither is a new
feature: both are the library disagreeing with itself.

- **`mappings/authoring.allowed_edges()` read the RAW json**, which holds
  canonicals only — so `mapping_validate` **refused** a relation declaring
  `is_overlain_by` while `Graph.add_edge` accepted that very edge without a
  warning. A validator stricter than the graph sends an author to fix something
  that was never wrong. It now reads `get_connections_datamodel()`, so the set is
  canonicals **+ reverses** (20 edges US→US where there were 13). The entry shape
  is unchanged and **grew** two keys: `is_canonical` and `canonical` (plus
  `is_symmetric`), so an editor can show a reverse AS a reverse. Honest limit,
  stated: a reverse carries its canonical's CIDOC mapping, because the datamodel
  declares the property once, in the canonical direction — and `cidoc_index()`
  still resolves CIDOC → canonical only.
- **`mapping_edge_groups()`** therefore lists both directions and each group now
  carries **`canonical_count`** beside `count`. The drift guard that watches the
  datamodel's size counts the canonical one: a reverse is the same property read
  backwards, not a 57th edge.

### Added (2026-09-19 — REV1, canonicalisation on import, OPT-IN)
- **`source_settings.canonicalize_reverse: true`** (default `false`) in
  `importer/base_importer._process_stratigraphic_relations`. On, a relation whose
  `edge_type` is a reverse is stored as its **canonical with source and target
  swapped**; a **symmetric** edge (`reverse: null` in the datamodel —
  `is_bonded_to`, `equals`, `has_same_time`, …) is **not** swapped and is
  deduplicated on the **unordered** pair. Everything else collapses by itself:
  the `{source}_{type}_{target}` id is already deterministic, so after the swap
  the two registrations of one fact ARE one id.
  - **Why it was needed**: a US card records the same physical relation from both
    sides — "1 copre 2" on one row, "2 coperto da 1" on the next — and that made
    **two edges for one fact**, with nothing downstream able to tell.
  - **Why only here**: this method is the single point where a relation read from
    a legacy table enters the graph. `Graph.add_edge` is untouched, so
    `import_graphml`, merge, contract and the crdt ops are **bit-identical**.
  - **Why opt-in**: EMStudio and Heriverse have not been re-vendored (Heriverse
    still ships datamodel 1.6.2 and has materials for edges that no longer
    exist). **It will become the default once they are aligned**, and removing
    the flag is when `Graph.add_edge` gets looked at again.
  - The truth table is **the datamodel**, read through
    `get_connections_datamodel()`. No second dictionary of inverses was written
    into this repo — a test asserts the four reverse names appear as literals
    exactly once, in the fallback branch. (pyarchinit-mini keeps its own
    `REVERSE_TO_FORWARD`, which maps `is_after` → `overlies` and so confuses the
    temporal plane with the physical one; that copy is the one to delete, not to
    copy.)
- **`STRATIGRAPHIC_EDGE_TYPES` is now derived**: a hand-written seed of six
  (`overlies`, `cuts`, `fills`, `abuts`, `is_bonded_to`,
  `is_physically_equal_to`) closed under the datamodel's `reverse`. It resolves
  to **the same ten names** it has always held — deriving changed nothing, which
  is the measure. `bonded_to` and `equals` are deliberately NOT seeded: widening
  what counts as edge-only would silently change mappings that name them.
- **`api.mapping_apply` reaches what the module function already accepted**:
  `injector` (who is answerable for what a call added) and the new `enrich_only`.
- **`enrich_only`** on `apply_mapping` / `api.mapping_apply`: the table importers'
  `_use_existing_graph` was forced to `False` unconditionally (rightly — passing a
  graph used to make every row vanish), which left pure enrich-only unreachable.
  It is now a parameter, default `False`, and it is forwarded to the inline
  importers too, which already had it in their constructors.


### Added (2026-08-24 — Shelf, Traccia A: role · URI-only · modes · EM Data table)
Four **additive** things on the shelf substrate that already exists. Nothing was
rebuilt and `LinkNode` was NOT renamed (breaking, coordinated, still deferred).

- **`role` on a shelf resource** — `ResourceNode.ROLES = ("comparandum",
  "internal_source")` + `set_role()` / `role()`, and it is **orthogonal** to the
  three fences and to residency: an own-study asset can be a comparandum, an
  external URI can be a source inside this study's own argument. Stated, never
  derived, and there is deliberately **no `effective_role`** — an unstated role is
  unset, not a default. Written by `add_to_shelf(role=…)`, reported by
  `list_shelf`, carried by `instantiate_from_shelf`, persisted in the em.json.
- **URI-only acquisition** — `JSON_config/acquisition_mappings/uri.json` +
  `acquisition.uri_record()` + `api.uri_acquisition_record()`: pasting a link
  makes a shelf entry that is the URI plus `access = {mode: open|subscribe,
  endpoint?}` and a D12 event. **No bytes are copied and no object store is
  touched**; the resource id is derived from the URI, so pasting it twice is one
  entry. New declared acquisition kind **`uri_reference`** in
  `em_visual_rules.json` (`download` would have recorded a retrieval that never
  happened) — consumers re-vendoring the rules pick it up.
- **`shelf_entry_status()`** — `{in_use, role, mode, used_by}`, DERIVED: `in_use`
  is the hatting reference-check, and it is literally the function the
  remove-cleanup already trusted (`referrers()`), so "is this in use?" has one
  answer. `mode` is `used_in_graph` / `only_shelf`, not a third state to keep in
  step.
- **`shelf_table()`** — the ShelfGraph as **EM Data rows** (typed columns, like
  the Units/Epochs/Documents sheets): name · media_type · residence[disk|minio|uri]
  · locator · role · mode · size · scope · residency · access · checksum. A
  read-model derived on every call, and deliberately **not** a sheet of
  `em_data.xlsx` (that importer fails fast on a missing sheet; the shelf's
  round-trip is the em.json).
- `api.add_to_shelf` now forwards `checksum` / `scope` / `residency` / `role` /
  `media_type` / `size` / `access` to the core, which already accepted them — a
  caller on the `api` surface could not state a fence at all before.


### Changed (2026-08-05 — BUGFIX-CONN3, connections datamodel → v1.6.7)
- Closes the two silent follow-ups of CONN2 (a legacy import edge and a shelf
  attach that both went quietly wrong once `has_visual_reference` moved to a
  LinkNode target).
- **Legacy import** (`import_graphml.enhance_edge_type`): a dashed
  `PropertyNode → DocumentNode` connector now imports as **`has_documentation`**
  (P70i_is_documented_in — the property is documented in the source), not the
  now-illegal `has_visual_reference`. The rarer `CombinerNode / bare ParadataNode
  → DocumentNode` is left as **`generic_connection` with a warning** (no honest
  single reading; a combiner cites no document and the DTC evidence chain
  property←combiner←extractor→document is NOT synthesised at import). Zero illegal
  edges produced.
- **Domain choice (declared)**: `has_documentation.source` was **widened** to add
  **`PropertyNode`** (judicious — a property may be documented in a source; P70i
  reads true). Extractor/other rules unchanged. Alternative considered and
  rejected: leaving PropertyNode→Document as warning+generic — but the honest
  typed reading (has_documentation) is available and preferred, so only the rarer
  combiner/paradata case falls back to generic. `em.ttl` needs no change
  (has_documentation maps directly to crm:P70i, no em: subproperty declared).
- **Shelf** (`shelf/core.py`): `hat_as_document` no longer offers
  `has_visual_reference` (`_DOC_ATTACH_EDGES` = extracted_from, has_documentation);
  a Document attaches via documentation/extraction, and a PropertyNode→Document
  now attaches as `has_documentation`. New **`hat_as_visual_resource`** attaches a
  **LinkNode** image via `has_visual_reference` from a PropertyNode — the correct
  home of a visual reference after CONN2 (no facet node: the visual resource IS
  the LinkNode). Datamodel-gated (a non-Property source is refused, not degraded);
  orphan cleanup via the shared `remove_resource` reference-check. Exposed on
  `api` and `shelf.__init__`.
- Tests: `test_importer_edge_hygiene` updated (property→document = documentation;
  combiner→document = generic+warning); `test_shelf_facets` +4
  (visual-resource attach / refuse-non-property / idempotent; document never uses
  visual_reference). Suite green, baseline FAILED unchanged.

### Changed (2026-08-05 — BUGFIX-CONN2, connections datamodel → v1.6.6)
- **`has_visual_reference` source/target corrected** (closes the two open domain
  questions from BUGFIX-CONN; E.D. 2026-08-05):
  - **SOURCE** narrowed from `[PropertyNode, ExtractorNode, CombinerNode,
    ParadataNode]` to exactly **`[PropertyNode]`**. Only a property (an asserted
    quale) is what a visual reference illustrates. Because Extractor/Combiner/
    Document are all subclasses of `ParadataNode`, dropping the generic parent
    now excludes them by class hierarchy. The extractor/combiner `denied_edges`
    added in v1.6.5 become redundant for this edge but are KEPT as a defensive
    guard (they still bite if the source is ever broadened back to `ParadataNode`).
  - **TARGET** changed from `[DocumentNode]` to **`[LinkNode]`** (the resource-layer
    image node, E73 Information Object / `ExternalResourceReference` — the same
    P67 hinge RM/RMDoc use via `has_linked_resource`). The oddity was a visual
    reference pointing at a source-document (E31); it now points at a visual
    resource, keeping `DocumentNode` = *fonte*.
- **CIDOC**: mapping stays `P138i_has_representation` with the target co-typed
  `E36_Visual_Item`. Now range-consistent: `E36 ⊂ E73` (LinkNode's base class),
  where it was strained for an `E31` Document. `rdf_exporter` co-typing is
  target-agnostic → no logic change, comment updated. `em.ttl`
  `em:hasVisualReference` domain `em:Paradata → em:Qualia`, range `E36` kept.
  **CIDOC confirmation still owed to Felicetti** (E36 as target class, as for USNt).
- **Follow-ups flagged** (need E.D. domain decisions, NOT silently rewired):
  (a) `import_graphml.enhance_edge_type` still maps `PropertyNode/Combiner/
  ParadataNode → DocumentNode ⇒ has_visual_reference` (legacy yEd heuristic, now
  produces an edge the datamodel refuses); (b) `shelf.hat_as_document` lists
  `has_visual_reference` among the Document-attach edges — it can no longer
  validate (target is LinkNode), so a paradata attach silently no longer attaches;
  a `hat_as_visual_resource(LinkNode)` + `has_visual_reference` path is the proper home.

### Added (2026-07-11 — .em.json v1 freeze)
- **`.em.json` v1 native format** (frozen 2026-07-11): `exporter/emjson_exporter.py`
  (header with format semver, generator, datamodel_versions, ontology_versions;
  FLAT graph section: nodes[]/edges[]; optional layout section) and
  `importer/emjson_importer.py` (Node.node_type_map factory, generic
  constructor binding, graceful degradation for unknown node types,
  count-stable round-trip). Round-trip test: `tests/test_emjson_roundtrip.py`.
  Design decision record: EMStudio repo, `docs/emjson-v1-draft.md` — the flat
  shape makes the bucket-enumeration bug class structurally impossible;
  the bucketed Heriverse payload (json_exporter) remains as legacy
  transitional format until Heriverse 1.6 adopts `.em.json`.
- `referenced_ontology_versions` header block in node and connections
  datamodels (2026-07-10).

### Changed (2026-07-10/11 — CIDOC serialisation pass, em.ttl → v1.6.1)
- RDF exporter: dual emission (em: subproperty + CRM predicate) generalised;
  CRMinf belief skeleton (J2→I2) with J4→I17 One-Proposition Set /
  J4→virtual-unit / J5→I6 expansion; has_visual_reference → P138i + E36
  co-typing; has_author → prov:wasAttributedTo; epoch edges → P10/P132
  (AP13/AP9 removed); SE re-anchored E5 → crmarchaeo:A5; confidence_level
  qualia → crminf:I6_Belief_Value.
- json_exporter: RSF, UL, USN, serUSD, BR added to the stratigraphic buckets.


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased] — v1.6.0 (in development)

### Architectural game-changer

This release adopts the **RDF triplestore as the persistent source of truth**
for EM data. The in-memory property graph (Blender, s3dgraphy Python) is now
treated as an editing cache; the triplestore is where the data lives. This
unblocks: (a) SPARQL queries as a daily-workflow capability, (b) multi-tool
read/write to the same dataset (Blender + web viewers + analytics + AI
pipelines), (c) formal HDT-O integration (every EM graph is an HC16 Heritage
Proposition Set attached to one or more HC2 HDTs).

The TTL export shipping in v1.6.0 is the **first** of three pieces (export,
endpoint read, endpoint write) — see `docs/s3dgraphy_roadmap.rst` for the
v1.6.0 → v1.7.0 plan.

### Added — Ontology layer

- **`em.ttl`** (`JSON_config/em.ttl`) — first formal Extended Matrix
  ontology. 30+ classes, 13 object properties, 245 triples. Declares the
  `em:` namespace (https://w3id.org/em/ontology#) — placeholder until a
  resolvable IRI is published. Covers: authors (HumanAuthor, AIAuthor +
  abstract Author), virtual SUs (VirtualSU + structural/non-structural/
  documentary/special-find variants), real SUs (NegativeSU, ReusedSpecialFind,
  DisplacedSpecialFind), series (4 types), events (StratigraphicEvent,
  TransformationSU, WorkingUnit, ContinuityNode), TimeBranch, RepresentationModel
  (+ 3 specializations), SemanticShape, Rights (License, Embargo, EMGraph),
  Qualia (paradata shell), Paradata head (I1_Argumentation), AP11 subproperties
  (abuts, cuts, fills, overlies, bondedTo, physicallyEquals).
- **`hdto_extension.ttl`** — minimal HDT-O subset aligned with ECHOES
  Deliverable D7.1 ("The Digital Commons"). 67 triples, 5 classes (HC1, HC2,
  HC14, HC15, HC16), 7 properties (HP1 + HP1i, HP3 + HP3i, HP29, HP33 + HP33i)
  with scope notes citing D7.1 §4. Namespace placeholder
  `https://w3id.org/hdto/ontology#`. Companion to em.ttl for HDT-O containment
  expression.
- **HDTNode** — new node type representing an HC2 Heritage Digital Twin
  inside an EM graph. Python class `HDTNode` (node_type='hdt') with
  heritage_entity_iri + valid_from/until. Hierarchically composable via
  `has_digital_twin_component` (HP3 inverse, transitive). EMGraph → HDT
  attachment via `contains_proposition_set` (HP33).

### Added — Node datamodel (v1.6.0)

- **`em_extension` block** on 29 of 41 node classes — declarative single
  source of truth for class IRIs (uri, rdf_type, subclass_of, extension_status,
  rationale). Replaces the deprecated `cidoc_s3d` field of invented strings.
- **AuthorNode split** into `AuthorNode` (human, em:HumanAuthor) and existing
  `AuthorAINode` (AI, em:AIAuthor). Both exported from `nodes/__init__.py`.
  Connections datamodel `has_author` already referenced AuthorAINode — the
  declaration was missing.
- **GraphNode** properly exported. New `container_nodes` section in node
  datamodel. Multi-typed as em:EMGraph + crm:E73_Information_Object +
  prov:Bundle + hdto:HC16_Heritage_Proposition_Set.
- **HDTNode** added to node datamodel `container_nodes` section.
- **Virtual SUs** semantic fix — `StructuralVirtualStratigraphicUnit`,
  `NonStructuralVirtualStratigraphicUnit`, `VirtualSpecialFindUnit` now
  declared as `crminf:I4_Proposition_Set` (propositional) not `crmarchaeo:A2`
  (physical, wrong semantics).
- **NegativeStratigraphicUnit** mapped to `crmarchaeo:A3_Stratigraphic_Interface`
  (the correct CRM class for a removal interface) — was wrongly mapped to a
  non-existent "A8 (Negative)".
- **DocumentaryStratigraphicUnit** declared as `em:DocumentaryVirtualSU`
  (a virtual SU inferred from documents) — was wrongly mapped to E31 Document
  (confused the SU with its sources).
- **ParadataNode** primary mapped to `crminf:I1_Argumentation` (was E31
  Document — paradata is reasoning, not documentation).
- **ExtractorNode** mapped to `crminf:I7_Belief_Adoption` (more specific
  than the previous E7 Activity).
- **CombinerNode** mapped to `crminf:I5_Inference_Making`.
- **TimeBranchNodeGroup** mapped to `em:TimeBranch ⊂ crm:E4_Period` with
  `em:contrastsWith` (symmetric). Was mapped to I2_Belief which over-typed
  (everything in EM is propositional by design).
- **RepresentationModel** subclasses (Doc, SF) declared as proper subclasses
  of `em:RepresentationModel` ⊂ crmdig:D1, with structural P138 target
  type constraints (was flat).
- **SemanticShape** mapped to `crmgeo:SP5_Geometric_Place_Expression`
  (was E36 Visual Item — too generic).
- **PropertyNode** declared as `em:Qualia` shell — the specific CIDOC class
  is resolved at serialization time by the qualia type (see em_qualia_types
  v4.0).

### Added — Canonical-edges series (v1.6.0)

The pyArchInit ↔ canonical-edge translation is now a single,
testable, public module (`s3dgraphy.sync.rapporti`). Physical
stratigraphic relationships (`copre`/`overlies`,
`taglia`/`cuts`, `riempie`/`fills`, `si appoggia a`/`abuts`,
`si lega a`/`is_bonded_to`, `uguale a`/`is_physically_equal_to`
and reciprocals) are **first-class canonical edges** in the
property graph; the pyArchInit `us_table.rapporti` column and
the new GraphML `physical_relationships` per-node attribute
are **serialisations only**, never verbatim copies on the
s3dgraphy node.

The series landed in four commits on `s3dgraphy_v1.6dev`:

- **`a934c7b`** — Extracted the vocabulary constants
  (`RAPPORTI_TO_EDGE_TYPE`, `EDGE_TYPE_TO_RAPPORTI_IT`,
  `RAPPORTI_SHORTHAND`, `EDGE_TYPE_DIRECTION_FORWARD`,
  `CANONICAL_UNIT_TYPES`, `CONTINUITY_UNIT_TYPES`) from
  `graphml_writer.py` and `graph_ingestor.py` into the new
  public `s3dgraphy.sync.rapporti` module. Back-compat shims
  keep the legacy private names importable from their original
  modules.
- **`c0303e5`** — Moved the dispatcher (`select_rapporti_label`,
  `resolve_unita_tipo_for_dispatch`, `strip_us_prefix`) and the
  parse/serialise APIs (`parse_rapporti`,
  `serialize_rapporti_from_edges`) into `sync.rapporti`. Defines
  the canonical 5-tuple `(edge_type, target_us, area, sito,
  swap)` that consumers iterate over.
- **`ce308d3`** — Migrated `graph_projector.py` to consume
  `parse_rapporti()` instead of its inline `ast.literal_eval` +
  direct lookups against the legacy constants.
- **`2823095`** — GraphML import + export for the
  `physical_relationships` per-node packed string (EM 1.6 palette
  format, byte-identical with the pyArchInit
  `us_table.rapporti` column). Three serialisations cohabit:
  - canonical edges in memory (single source of truth)
  - graph-level `_s3d_physical_relations` JSON side channel
    (richer, carries per-edge author/document attributes —
    authoritative on import when present)
  - per-node `physical_relationships` packed string
    (interoperability fallback for yEd-hand-authored files or
    pyArchInit-side bridges)

Test surface: +57 tests across
`tests/sync/test_rapporti_vocabulary.py` (13),
`tests/sync/test_rapporti_parse_serialize.py` (38) and
`tests/sync/test_graphml_physical_relationships_d13.py` (6).
The series has zero regressions vs. baseline (385 passed / 8
pre-existing failures / 37 skipped).

Cross-tracker references:
- `s3dgraphy #16` — canonical edges + reciprocity + paradox
  detection (covered).
- `EM-blender-tools #30` — companion yEd palette change
  (`physical_relationships` on US-type nodes; the s3dgraphy
  palette mirror at `src/s3dgraphy/templates/em_palette_template.graphml`
  is updated by commit `1c195f1`).

### Fixed — v1.6.0.dev8: multilingual `unita_tipo` recognition (PR #22, closes #21)

pyArchInit localises the US / USM `unita_tipo` codes per UI language
(its `pyarchinit_i18n_stratigraphic.UNIT_TYPE_ABBREV` is the source of
truth), so a non-Italian site was silently broken by the canonical-
edges series shipped in dev7: rows with `SU` / `WSU` / `SE` / `MSE` /
`UE` / `UEM` / `USZ` / `ΣΜ` / `ΤΣΜ` were skipped by the stratigraphic
gating in `graph_projector.populate_graph`, and any surviving edges
fell through to the `>>` / `<<` shorthand in
`serialize_rapporti_from_edges` because `CANONICAL_UNIT_TYPES` only
recognised the Italian codes `{"US", "USM"}`.

Fixed by Enzo Cocca (PR #22, closes #21):

- **`s3dgraphy.sync.rapporti.UNITA_TIPO_CANONICAL`** — new dict
  mapping `localized → canonical` for the US / USM atoms (it/fr/ro ·
  en/ar · de · es/ca/pt · ro-USM · el). Doubles as the normalisation
  source via the new public `canonical_unita_tipo()` helper, and
  `CANONICAL_UNIT_TYPES` is now derived from the dict keys so the two
  never drift. Co-located with the existing prefix-strip regex that
  already enumerates `SU|SE|WSU|MSE|UE|…`.
- **`graph_projector.populate_graph`** — the stratigraphic-row gating
  and the node-class factory route `unita_tipo` through
  `canonical_unita_tipo()`. The original code stays verbatim in
  `attributes['unita_tipo']` so round-trip writes back the
  site-language value byte-identically; only the dispatch and gating
  read through the alias map.
- **`serialize_rapporti_from_edges`** — anchors the d13 verbose label
  on the source row's own `rapporti` term (capitalised), so the
  packed string byte-matches the originating `us_table.rapporti` in
  the site's UI language (`Covers` / `Couvre` / `Bedeckt` / …).
  Falls back to the canonical Italian verbose when the source carries
  no `rapporti` attribute (e.g. yEd-imported graphs). Virtual units
  (`>>` / `<<`) and continuity (`>` / `<`) keep their shorthand.

Real-data verification on a non-Italian site (Al-Khutm, English UI,
485 US rows): **before** the fix `populate_graph` built 6 nodes / 0
stratigraphic edges (only the few rows still coded `US`/`USM`); **after**,
485 nodes / 2368 edges with all-English d13 labels (`Covers`,
`Covered by`, `Cuts`, `Cut by`, `Abuts`, `Same as`, `Fills`, …), zero
canonical-Italian leak.

Test surface: +2 files in `tests/sync/` —
`test_rapporti_multilingual_d13.py` (parametrised over 11 language
variants, pins multilingual verbose dispatch + localised d13 +
shorthand preservation + yEd fallback) and
`test_graph_projector_multilingual.py` (mutates the `mini_volterra`
fixture to SU/WSU + English `rapporti` and asserts end-to-end node
build + edge build + original-code preservation + English d13 + no
Italian leak). Zero regressions vs the post-dev7 baseline.

The pyArchInit-side stop-gap (vendored copy of `sync.rapporti` +
boot-time monkeypatch on the GraphML exporter import) can be dropped
once `s3dgraphy-1.6.0.dev8` is on PyPI and EM-blender-tools bumps the
bundled wheel.

Broader follow-up: the multilingual story for free-text content (RDF
literal `@xx` language tags on labels / descriptions / notes, CIDOC /
SKOS-aligned, `em.ttl` translations) is spun out as DP-63 on the
dev-site, scoped to EM 1.6 under the StratiGraph umbrella. PR #22's
`UNIT_TYPE_ABBREV`-as-source-of-truth pattern is the precedent for
propagating the source UI language into the importer plumbing.

### Fixed — multilingual relationship-label vocabulary

Follow-up to PR #22: the *unita_tipo* codes became multilingual, but the
stratigraphic **relationship** labels in `RAPPORTI_TO_EDGE_TYPE` were still
Italian + partial English. So `parse_rapporti()` silently dropped a label
from any other UI language — a graph projected from a German / Greek / etc.
site built no edges, and a reciprocity round-trip failed (the English
reciprocal of "Abuts" is "Supports" = `is_abutted_by`, which had no entry at
all). Fixed by Enzo Cocca:

- `sync/rapporti.py`: add `"supports" → is_abutted_by`, and fold the full
  10-relations × 10-languages EM/pyArchInit vocabulary (it/en/de/es/fr/ar/
  ca/ro/pt/el) into `RAPPORTI_TO_EDGE_TYPE` via a small index→edge-type table
  (`_REL_INDEX_EDGE_TYPE` + `_REL_TERMS_BY_LANG`), `setdefault` so explicit
  aliases (e.g. `"bonds with"`) are preserved. Lowercased keys to match the
  parser's lookup. Additive — no public-API or behaviour change for existing
  IT/EN labels.
- Test: `tests/sync/test_rapporti_multilingual_relationships.py` — every
  language term resolves to its canonical edge type, `parse_rapporti`
  recognises labels across all 10 languages, and the reciprocal index pairs
  map to inverse edge types.

### Added — Connections datamodel (v1.6.0)

- Bug fix: typo `ProperrtyNOde` → `PropertyNode` in
  `is_in_paradata_nodegroup.allowed_connections.source`.
- Semantic fix: `has_documentation.mapping.cidoc` changed from
  `P104_is_subject_to` (wrong — P104 means subject to a legal right) to
  `P70i_is_documented_in` (canonical "is documented by").
- `has_timebranch` marked **deprecated** with rationale: duplicate of
  `is_in_timebranch`. Verified usage: `is_in_timebranch` is canonical
  (import_graphml.py:1510, graphml_patcher.py:73); `has_timebranch` lives
  only in JSON config. Scheduled removal in 1.7.0.
- **+4 HDT-O containment edges**: `has_digital_twin` (HP1),
  `has_digital_twin_component` (HP3 inverse, transitive),
  `contains_proposition_set` (HP33), `has_digital_object_part` (HP29).
- Components list aligned with node datamodel (HDT-O, PROV-O added).

### Added — Qualia types (v4.0)

- Verified all existing v3.0 CIDOC-CRM mappings (all correct).
- **+50 new qualia** across categories: volume/area/circumference (dimensional);
  color, texture, finish, patina, hardness, porosity (material); damage_type,
  fragility, completeness (state); tool_marks, joining_technique (technical);
  bounding_box, footprint_area (spatial); duration, terminus_post_quem,
  terminus_ante_quem, relative_chronology (temporal); ceremonial/ritual/
  defensive/domestic/symbolic functions (telic); school, period_attribution
  (stylistic); provenance_history, exhibition_history, publication_history
  (administrative).
- **NEW SUBCATEGORIES**: iconographic (iconographic_subject, narrative_content,
  iconographic_program), semantic (aesthetic_value, religious_significance,
  monumental_status, attribution), ownership (current_custodian, ownership_chain).
- **NEW CATEGORY epistemic** — meta-qualia central to the EM paradata model:
  confidence_level (E54 percentage), certainty_level (E55 enum), uncertainty_factors,
  methodology_used (E29), validation_method, source_quality, primary_contributor
  (E39 ref), review_status, last_modified (E52).

### Added — Visual rules + palette

- Visual styles for `AUTH_AI` (cyan star), `LIC` (gold shield),
  `EMB` (red dashed octagon), `GRAPH` (gray dashed rounded rectangle).
- Palette label prefix `G.` for GraphNode (alongside existing AI./A./LI./EB.).

### Added — RDFExporter (exporter/rdf_exporter.py)

- First serialization pipeline from s3dgraphy Graph to RDF.
- Five formats: Turtle, N-Triples, N-Quads, TriG, JSON-LD, RDF/XML.
- Multi-typing emission from `em_extension.subclass_of`.
- **Conditional PropertyNode mapping** — qualia type drives the CIDOC class
  (height → E54_Dimension, aesthetic_value → crminf:I4_Proposition_Set, etc.).
- AP11 physical-relation discrimination: emits both the specific subproperty
  (em:abuts) AND the generic crmarchaeo:AP11 (so consumers without subproperty
  inference still see the relation).
- Deprecated edges skipped on write.
- Named-graph wrapping per s3dgraphy Graph (one named graph per Graph).
- Stats: graphs, nodes, edges_emitted, edges_skipped_deprecated, edges_unmapped,
  nodes_unmapped, parent_hdt_bindings.

### Added — v1.6.1: parent HDT binding

- `RDFExporter(parent_hdt_iri=...)` — every exported EMGraph emits
  `hdto:HP33i_is_proposition_set_of <parent>` + parent type triple.
- IRI validation: requires absolute http(s)/urn IRI, ValueError on malformed.
- EM-blender-tools `EXPORT_OT_rdf` operator wires the scene field through.

### Fixed — v1.6.0.dev5: RDF qualia lookup (exporter-only, importer unchanged)

Architectural note: this fix lives entirely in the RDF exporter. The
graphml importer is left intact — it preserves raw graphml data
(``name``, ``description``, raw ``value``, ``property_type``). Semantic
enrichment via the qualia vocabulary happens at serialization time,
where it belongs (separation of concerns: importer = data, exporter =
semantics).

- **`exporter/rdf_exporter.py::_Datamodel.get_qualia_crm_iri`** — 4-step
  graceful lookup so the RDF conditional mapping survives common yEd label
  conventions:
  1. exact match (`"height"` → E54_Dimension)
  2. dot-split last segment (`"Dimension.height"` → "height" → E54_Dimension)
  3. lowercase fallback (`"Height"` → "height" → E54_Dimension)
  4. lowercase + dot-split combined (`"Dimension.Height"` → E54)
- **`exporter/rdf_exporter.py::_compute_primary_iri`** — for PropertyNodes,
  resolves the lookup key in two steps:
  1. ``node.property_type`` if explicitly set (non-default — anything
     other than the constructor sentinel "string")
  2. ``node.name`` (the yEd NodeLabel — qualia identifier in EM convention)
  This means files exported with the structured ``_s3d_property_metadata``
  side channel (which populates ``property_type``) AND legacy / converted
  graphml (where only ``name`` is populated) both work transparently.
- **`exporter/rdf_exporter.py::_serialize_type_specific`** for property —
  value resolution falls back from ``node.value`` to ``node.description``
  when the former is empty/None. yEd ARTIFACT_TYPE_ANNOTATION nodes have
  no dedicated "value" socket, so the description field commonly carries
  the value text (e.g. ``description="2013"`` for an absolute_time_start
  PropertyNode). The legacy URL-as-value convention is also honoured via
  ``node.value`` (which the importer still populates from the URL).
- The same NodeLabel fallback feeds ``em:hasQualiaType`` so SPARQL queries
  by qualia type work even on legacy graphml without the side channel.

Verified on Templu Mare graphml labels (absolute_time_start →
E52_Time-Span, Dimension.height → E54_Dimension, aesthetic_value →
crminf:I4_Proposition_Set). Custom labels like "lenght_pipe" correctly
fall back to the generic PropertyNode default (em:Qualia +
crm:E1_CRM_Entity).

### Added — RSF (Reused Special Find)

- **`RSF` (Reused Special Find)** — new stratigraphic node type for re-used
  architectural / decorative elements (spolia). Octagon, red border
  (`#9B3333`), white fill — visually a sibling of `SF` (yellow border) and
  `VSF` (gold border), distinguished by colour. Originating Development
  Project: DP-26 (spolia project, last DP before the EM 1.5 cut). Wired
  through the full pipeline: Python class `ReusedSpecialFind` in
  `nodes/stratigraphic_node.py`, JSON datamodel entry under
  `stratigraphic_nodes.StratigraphicNode.subtypes` (family `real`,
  `is_series=false`), `em_visual_rules.json` style entry, and
  `STRATIGRAPHIC_CLASS_MAP` registration. Family classification
  (`real` / non-series) flows through the existing `classification.py`
  accessors (`is_real("RSF")` returns `True`) without code change.
- **`serUSD` export dispatch** — palette template `^USD\d+$` shape
  `ellipse` (border `#D86400`) now correctly dispatches to `serUSD` on
  export, mirroring the existing import logic in
  `utils/utils.py::convert_shape2type`. Closes the export-side asymmetry
  flagged in `PALETTE_AUDIT.md` § 4 — the `serUSD` *class*,
  *datamodel JSON*, *visual rules*, and *importer rule* all pre-existed,
  but the exporter was silently routing the ellipse stencil to its
  default fallback. Round-trip identity now holds for `serUSD` graphs.

### Changed
- `convert_shape2type` (importer) extended with the `RSF` recognition rule
  (`octagon` + `#9B3333`). `serSU` continues to use the same border colour
  but the shape qualifier (ellipse vs octagon) keeps the two unambiguous.
- `_PALETTE_DISPATCH_RULES` (exporter) extended with `RSF` (`^RSF\d+$` +
  octagon) and `serUSD` (`^USD\d+$` + ellipse) rules. Order preserves the
  first-match-wins contract: the new `serUSD` rule sits next to the
  existing `USD` roundrectangle rule, the new `RSF` rule next to `SF`/`VSF`.
- `_REQUIRED_PALETTE_TYPES` now includes `RSF` and `serUSD`, so a future
  palette template that drops either stencil triggers the existing
  `S3DgraphyPaletteWarning` plus default-visual-properties backfill rather
  than silently degrading.
- `NodeRegistry._default_visual_properties_dict()` ships fallback
  `NodeVisualProperties` for `RSF` and `serUSD` so the registry never
  returns `None` for these types even when the palette resource is
  unreachable.
- `s3Dgraphy_node_datamodel.json` bumped to internal version `1.5.4`
  (description annotated with the RSF addition). The package-level
  `__datamodel_version__` (`1.5.5`, connections datamodel) is intentionally
  unchanged — it is governed by a separate file.
- `em_visual_rules.json` bumped to internal version `1.5.2` with a
  changelog entry for the RSF style.

### Changed
- **GraphML export — semantic dispatch for stratigraphic node types**. The
  stratigraphic export pipeline (`exporter/graphml/node_registry.py`) now
  selects palette template elements by `<y:NodeLabel>` pattern matching
  (e.g. `USM\d+` rectangle → `US`, `USM\d+` ellipse → `serSU`,
  `USV\d+` parallelogram → `USVs`, `USV\d+` hexagon → `USVn`,
  `USV\d+` ellipse → `serUSVn`) instead of the GraphML-internal id
  (`n1..n9`). This aligns the export side with the existing semantic
  import logic (`utils/utils.py::convert_shape2type`), decouples the
  palette visual ordering from the writer, and removes the silent
  degradation that occurred when a node label could not be matched
  after the palette was reordered in yEd.

### Fixed
- Unrecognised palette labels in export no longer fall back silently to
  `US` with a white/red rectangle. The new dispatch emits an explicit
  `S3DgraphyPaletteWarning` (subclass of `UserWarning`) indicating the
  label and the chosen fallback, asking the caller to register the
  pattern in `node_registry._PALETTE_DISPATCH_RULES`.
- The registry also warns at load time if the palette template ships
  without one of the canonical stratigraphic stencils (`US`, `serSU`,
  `USD`, `USVs`, `USVn`, `serUSVn`, `SF`, `VSF`, `TSU`); missing types
  are backfilled from the hardcoded defaults so callers never get
  `None` for a known stratigraphic type.

### Migration notes
- No public API change. `NodeRegistry`, `get_visual_properties()`,
  `get_shape_for_type()`, `get_colors_for_type()` keep their
  signatures. Round-trip identity preserved for all existing GraphML
  fixtures shipped in this repository, including the live
  `templates/em_palette_template.graphml`.
- Tools generating palette templates with non-canonical labels (e.g.
  `MyCustomUS01`) should add their pattern to
  `_PALETTE_DISPATCH_RULES` in 0.1.42 to avoid the new
  `S3DgraphyPaletteWarning` and obtain correct visual rendering.
- The new public symbol `S3DgraphyPaletteWarning` (subclass of
  `UserWarning`) can be used by downstream code (Blender add-ons,
  CI gates) to filter or escalate palette mismatches via the standard
  `warnings` module.

### Tests
- New `test_palette_dispatch.py` covers: round-trip identity per
  stratigraphic type (US, USVs, USVn, SF, VSF, **RSF**, USD,
  **serUSD**, serSU, serUSVn, TSU), live-template backward
  compatibility, order independence (palette with shuffled `<node id>`
  still resolves to the right types), `S3DgraphyPaletteWarning`
  emission on unknown `node_type`, and missing-required-type detection
  with default backfill.
- Dedicated tests for the RSF / serUSD additions: class registration
  (`STRATIGRAPHIC_CLASS_MAP`), dispatch table content, USD-vs-serUSD
  shape disambiguation, `convert_shape2type` round-trip on the new
  rules, and `em_visual_rules.json` carrying the RSF and serUSD
  styles. All 47 palette-dispatch tests + 7 classification tests pass.

### Originating analysis
- Architectural audit `PALETTE_AUDIT.md` (May 2026, EM-blender-tools
  repo): identified the export-side positional dispatch as a
  silent-failure fragility for palette reordering at the 1.5 cut.
  Variante A applied; the related `serUSVs` synthesis (cloned from
  `serUSVn` with blue border) is preserved unchanged. The audit also
  surfaced the `serUSD` export-side asymmetry — closed in this
  release.
- DP-26 (spolia project, EM dev tracker): the typological framing of
  RSF as a re-used physical element with a stratigraphic identity of
  its own (real / non-series), distinct from `SF` (in-situ
  repositionable) and `VSF` (virtual reconstruction). Last
  Development Project before the EM 1.5 cut; formalised here as a
  first-class stratigraphic subtype.

## [0.1.41] — 2026-05-09

### Added — `LocationNodeGroup`: spatial / locational membership

A new group-node type closing the structural gap between activity-based and
location-based grouping in the EM formalism. Originating discussion:
[issue #5](https://github.com/ExtendedMatrix/s3Dgraphy/issues/5) by
[@enzococca](https://github.com/enzococca) — the PyArchInit integration
exposed cases (toponyms, study sectors, functional rooms — and walls between
two rooms) where activity grouping alone was not enough. Many thanks to Enzo
for the precise framing.

- **New class `LocationNodeGroup`** in `src/s3dgraphy/nodes/group_node.py`
  (subclass of `GroupNode`). Re-exported from `s3dgraphy.nodes` and listed
  in the package `__all__`.
  - Required field `kind ∈ {toponym, study, functional}` — the *epistemic
    plane* of the location. The three coexist on the same node and may
    compose. `ValueError` if the kind is not in the allowed set.
  - Field `propagation` defaulting to `"additive"` (memberships compose;
    none overrides) — distinct from `EpochNode`, which is substitutive
    (finest-grained wins).
  - Hierarchy: a `LocationNodeGroup` can itself be `is_in_location` of
    another `LocationNodeGroup` (Pompei → Sector 4 → Casa del Fauno →
    Room 12).
- **Datamodel JSON v1.5.3** (`JSON_config/s3Dgraphy_node_datamodel.json`):
  registers `LocationNodeGroup` under `group_nodes.GroupNode.subtypes`
  with abbreviation `LNG`, label `"Location Node Group"`, and the full
  `kind` / `propagation` field schema. CIDOC-core mapping: `E53 Place`,
  classified by `E55 Type` instances via `P2_has_type`. The `propagation`
  field is explicitly marked as schema-level metadata, *not* serialised to
  the triplestore (no per-instance triple).
- **Connections datamodel JSON v1.5.5**
  (`JSON_config/s3Dgraphy_connections_datamodel.json`): new `is_in_location`
  edge with `includes_location` reverse, full `allowed_connections.source`
  list (`StratigraphicNode`, `ParadataNode`, `ParadataNodeGroup`,
  `DocumentNode`, `ExtractorNode`, `CombinerNode`, `PropertyNode`,
  `LocationNodeGroup`) and `target = LocationNodeGroup`. Context-sensitive
  CIDOC mapping: `P53_has_former_or_current_location` for
  *node → location* and `P89_falls_within` for the recursive
  *location → location* hierarchy. Optional edge attribute
  `is_primary: bool` (default `false`) declared in the new `attributes`
  block on the edge definition; one `is_primary=true` edge per source is
  the rendering hint for em-graph yEd group-folder selection.
- **Visual rules v1.5.1** (`JSON_config/em_visual_rules.json`): new
  `LocationNodeGroup` entry — dashed round-rectangle, fill `#F5F5F5`,
  label at top, with per-`kind` border colour modifiers
  (toponym `#888888`, study `#3A5A8C`, functional `#000000`). New
  `is_in_location` edge style with a `primary_modifier` override
  (`width: 2`, `color: #444444`, solid line) applied when
  `is_primary=true`.

### Triplestore mapping discipline

Every new identifier carries either a CIDOC-core mapping (preferred) or a
proposed `s3d:` extension URI with an explicit `extension_status: proposed`
marker and a written `rationale` justifying why CIDOC-core (and the
existing extensions CRMarchaeo / CRMsci / CRMinf) do not already cover the
concept:

- `LocationNodeGroup` itself maps to vanilla `E53 Place`
  (no new s3d class).
- `kind` is expressed by `P2_has_type` to one of three reserved
  `E55 Type` instances: `s3d:KindToponym`, `s3d:KindStudy`,
  `s3d:KindFunctional`. CIDOC-native composition; no new property URI.
- `is_in_location` reuses CIDOC-core `P53` / `P89`. No s3d predicate.
- `is_primary` edge attribute is the only genuinely new RDF property —
  carried as `s3d:isPrimary` with rationale "no CIDOC equivalent —
  disambiguates UI rendering of m:n membership on yEd group folders".
- `propagation` is declared schema-level only and is not serialised to
  triples.

> **Stability disclaimer.** The `s3d:` namespace identifiers introduced in
> this release (`s3d:KindToponym`, `s3d:KindStudy`, `s3d:KindFunctional`,
> `s3d:isPrimary`) are *candidate primitives* for a forthcoming CIDOC-S3D
> extension (in the spirit of CRMarchaeo / CRMsci / CRMinf). Their
> stability is **proposed**, not final. Consumers should expect potential
> URI rename when the extension is formalised, and read the
> `extension_status: "proposed"` field in the JSON datamodel as a
> machine-readable marker of this commitment level.

### Documentation

The `extendedmatrix-doc` manual gains a new `Location` concept page (the
first to follow the *concept-first* template: overview → em graph → s3d
graph → em_data → CIDOC mapping → examples) and a new general `em_data`
section that the page cross-links to. The AI / StratiMiner section in
`knowledge_tree.rst` now points to `em_data` for the workbook conventions.

### Naming conventions

Going forward, single-axis sub-discrimination on nodes uses the field name `kind` (Python instance attribute and JSON datamodel field). The existing instance attributes `RepresentationNode.type` and `SemanticShapeNode.type` are preserved for backward compatibility; **new code should prefer `kind`** to avoid collision with the structurally reserved `node_type` (class identity, registered in `Node.node_type_map`) and with `rdf:type` / `P2_has_type` in the CIDOC mapping path.

Multi-axis classification (cf. `DocumentNode.role` / `content_nature` / `geometry`) continues to use semantically named axes — `kind` is reserved for single-axis cases.

A future release may unify `RepresentationNode.type` and `SemanticShapeNode.type` under `kind` with a deprecation cycle; this 0.1.41 makes no breaking changes.

### Added — Stratigraphic classification refactor (2026-04)

- **Datamodel JSON v1.5.2** (patch, additive)
  (`JSON_config/s3Dgraphy_node_datamodel.json`): every stratigraphic
  subtype now carries two additional fields — `family`
  (`"real"` / `"virtual"` / `null`) and `is_series` (bool). Bumped
  from v1.5.1 as a patch — these are additive metadata fields that
  existing consumers ignore, no breaking changes to the formalism
  (the EM formal language stays at 1.5). Lets downstream tools
  (GraphML importer BR-handling, EM-blender-tools pickers /
  filters / material maps) consume classification metadata without
  hardcoding type lists.
- **`s3dgraphy.classification` module**: JSON-driven API re-exported
  from the package root:
  - `get_family(node_type)` / `is_real(nt)` / `is_virtual(nt)` /
    `is_series(nt)` accessors reading the datamodel JSON.
  - `get_subtype_info(nt)` / `iter_subtypes()` for metadata walks.
  - Frozenset constants computed from the JSON:
    `REAL_US_TYPES`, `VIRTUAL_US_TYPES`, `SERIES_US_TYPES`,
    `ALL_US_TYPES`.
- **Negative Stratigraphic Unit**: new
  `NegativeStratigraphicUnit` class in
  `nodes/stratigraphic_node.py` with `node_type="USN"`,
  classified as `family="real"` / non-series. Surfaced in
  `em_visual_rules.json` with a dashed-rectangle variant so it
  renders distinct from a positive US in yEd. Replaces the ad-hoc
  `US_NEG` placeholder that lived only in EM-blender-tools.
- **Extended `STRATIGRAPHIC_CLASS_MAP`** (`utils/utils.py`): added
  `UL → WorkingUnit` (was silently missing from the map, causing
  downstream factories to fall back to the generic
  `StratigraphicNode`) and `USN → NegativeStratigraphicUnit`.
- **New qualia `proxy_geometry`** in
  `JSON_config/em_qualia_types_additions.json` under
  `physical_material.dimensional` (alongside `area` / `volume`) —
  canonical property name for the 7-point bounding box that the
  Proxy Box Creator (EM-blender-tools) writes as a PropertyNode.
- **Test `test_stratigraphic_classification.py`**: locks seven
  invariants between the Python map and the JSON datamodel:
  abbreviations aligned both ways, every subtype declares a valid
  `family`, `is_series` matches the `ser` prefix convention, the
  classification accessors agree with the JSON, USN registered
  correctly, pre-computed sets consistent with per-node
  accessors, and `iter_subtypes` yields every entry. Brings the
  suite to 20/20 green.

### Fixed — GraphMLPatcher paradata rendering (2026-04)

- **Extractor / Combiner NodeLabel** positioned at Corner-NorthWest
  via `modelName="corners"` + `modelPosition="nw"` +
  `borderDistance="0.0"` + `underlinedText="true"` — matches the
  reference TempluMare graphml and the full-export
  `node_generator.py`. Previously the patcher wrote neither
  attribute, so yEd defaulted to `Internal:Center` and the
  extractor id overlapped the SVG glyph.
- **ParadataNodeGroup positioning**: the `_add_group_realizer`
  Geometry was hardcoded to `(0, 0)`. The new
  `_seed_group_realizer_positions` rewrites the realizers'
  `x`/`y` with the epoch-derived position returned by
  `_calculate_node_position`, so PD groups are anchored in the
  right swimlane row instead of floating outside the Table.
- **ParadataNodeGroup / ActivityNodeGroup containment**:
  `add_new_nodes` now runs as a two-pass routine — first inserts
  new group containers (indexing their nested `<graph>` elements
  plus those of pre-existing groups discovered through
  `original_id`), then routes every other new node into the
  matching container based on `is_in_paradata_nodegroup` /
  `is_in_activity` edges. Result: US + PD + Extractors + Combiner
  + PropertyNode + Document-instance are physically nested under
  the correct yEd group at save time, not dumped in the top-level
  graph.
- **`_calculate_node_position` for ParadataNodeGroup**: special
  case that inherits the host US's epoch via
  `has_paradata_nodegroup` (reverse lookup) so the Y coordinate
  is the US's swimlane band, not `(0, 0)`.

### Added

- **Hybrid-C auxiliary lifecycle (Phase 1 + 3)**. New module
  ``s3dgraphy.transforms.aux_tracking`` providing the bookkeeping
  primitives that let the GraphML exporters distinguish **graph-
  native** content from **auxiliary-injected** content (DosCo, emdb,
  pyArchInit, sources-list, resource-folders):
  - ``mark_as_injected(obj, injector_id)`` / ``is_injected(obj)``
    — tag enrichment children (PropertyNodes, LinkNodes, etc.)
    added by an auxiliary.
  - ``record_attribute_override(node, attr, injector_id, original_value)``
    + ``freeze_aux_value(node, attr)`` — capture the pre-aux value
    when an auxiliary mutates a host-node attribute (e.g. DosCo
    setting ``DocumentNode.url``).
  - ``apply_override_reversal_policy(graph)`` — per-attribute
    policy used by the **volatile** save: if the current value
    still matches the aux value, revert to the pre-aux original;
    if the user re-edited the attribute afterwards, keep the
    user value and drop the override record.
  - ``strip_injected_content(graph)`` — remove every node/edge
    tagged ``injected_by`` (volatile save).
  - ``clear_aux_tags(graph)`` — drop all ``injected_by`` and
    ``_aux_overrides`` records (bake save, promotion to graph-
    native).
  - Orphan reporting: ``push_orphan`` / ``iter_orphans`` /
    ``clear_orphans`` — track aux rows whose key ID did not match
    any host in the graph (UI surfacing deferred to Phase 2).
- **``GraphMLExporter.export(path, persist_auxiliary=False)``** and
  **``GraphMLPatcher.patch(path, persist_auxiliary=False)``** new
  ``persist_auxiliary`` parameter:
  - ``False`` (default, **volatile**): apply the reversal policy
    and strip injected content before emitting. The on-disk
    GraphML reflects only graph-native state; on next reload the
    auxiliaries re-inject cleanly.
  - ``True`` (**bake**): emit everything verbatim and clear the
    ``injected_by`` / ``_aux_overrides`` bookkeeping. The
    enrichment layer becomes graph-native going forward.
- **User's Blender-native edits never lost**. The volatile save
  preserves new nodes the user adds in Blender (no ``injected_by``
  tag) and keeps attribute values the user manually re-edited
  after an auxiliary applied (detected by comparing current value
  to frozen aux value).
- Locked in by 7 unit scenarios in ``test_aux_tracking.py`` and 3
  end-to-end round-trips on the Great Temple GraphML
  (``test_aux_roundtrip_graphml.py``), covering scenarios α
  (volatile revert), β (user re-edit wins), γ (Blender-native
  additions survive) and bake-then-reload idempotence.
- **Phase 1b hookup plan** for the existing auxiliary importers
  (DosCo / emdb / pyArchInit / sources-list / resource-folders)
  documented in
  ``docs/dev-projects/HYBRID_C_PHASE_1B_IMPORTER_HOOKS.md``;
  code changes deferred to the next sprint.

### Changed

- **AI extraction prompt rewritten for the unified schema** (v5.0,
  breaking change). The StratiMiner prompt at
  ``s3dgraphy/data/AI_EXTRACTION_PROMPT_v4.md`` (filename kept for
  backward-compatible imports) now describes the single-file
  ``em_data.xlsx`` output with 5 sheets, explicit
  ``AUTHOR_KIND_N ∈ {author, extractor}`` distinguishing claims
  transcribed from the document author vs claims newly derived by the
  AI, and per-claim attribution on stratigraphic relations. Ships an
  updated validation script that checks cross-sheet referential
  integrity, duplicate triples, missing COMBINER_REASONING, and
  stratigraphic cycles. Also documents a **stratigraphy-only mode**
  for legacy archaeological databases where paradata attribution is
  not yet available (curator as sole author, no extractor chain).

### Added

- **GraphMerger extended for the paradata layer** (Phase B — xlsx ↔
  graphml merge). The existing ``s3dgraphy.merge.graph_merger.GraphMerger``
  now covers every node/edge class produced by the unified xlsx
  pipeline, not just stratigraphic units. New conflict types:
  - ``qualia_added``, ``qualia_changed``,
    ``qualia_attribution_added`` — PropertyNode claims (matched per
    ``(unit_name, property_type)``).
  - ``author_added`` / ``author_changed`` and ``document_added`` /
    ``document_changed`` — catalog entries matched by short code
    (``A.01``, ``D.01``). ``AuthorAINode`` vs ``AuthorNode`` kind drift
    is flagged but not auto-applied.
  - ``epoch_added`` / ``epoch_changed`` — Epoch matched by name;
    differences in ``start_time`` / ``end_time`` / color are each
    reported as a dedicated conflict with a ``subfield`` hint in
    ``Conflict.extra``.
  - ``edge_attribution_added`` / ``edge_attribution_changed`` — diffs
    on the ``edge.attributes`` dict (``authored_by_N``,
    ``authored_kind_N``, ``document_N``) of relation edges; lets the
    merger propagate per-claim relation attribution from an incoming
    xlsx into an existing graphml.
  - ``Conflict.extra: Dict[str, Any]`` — new field on the dataclass
    (default empty) that carries per-conflict payload (property type,
    target endpoint, attribute key, subfield, …). Backward-compatible
    for existing callers.
  - ``apply_resolutions`` handles all new types: qualia changes copy
    the full PropertyNode subtree (PN + provenance chain) from the
    incoming graph, with catalog nodes (Author / Document) reused
    from the host to avoid duplication. Catalog/epoch add-and-change
    apply directly; edge attribution writes to ``edge.attributes``.
  - Locked in by 8 synthetic scenarios (``test_graph_merger.py``)
    plus a real-data smoke test on the Templu Mare graphml
    (export → modify → re-import → merge) covering author rename,
    author addition, and new qualia row.
- **Unified xlsx writer** (Phase B — complete round-trip). New module
  ``s3dgraphy.exporter.unified_xlsx_exporter`` exporting a full graph
  back to an ``em_data.xlsx`` with the 5-sheet schema. It is the
  inverse of :class:`UnifiedXLSXImporter`: walks the in-memory graph
  and emits Units / Epochs / Authors / Documents catalogs plus a
  long-table Claims sheet that reconstructs the paradata chain
  (``PropertyNode → has_data_provenance → Extractor / Combiner →
  has_author``) as ``(EXTRACTOR_i, DOCUMENT_i, AUTHOR_i,
  AUTHOR_KIND_i)`` triples. Combiner rows get 2 triples plus
  ``COMBINER_REASONING``; stratigraphic relations read their
  attribution from the edge's ``attributes`` dict. Only the
  canonical direction of each relation pair is emitted (``overlies``
  but not ``is_overlain_by``) — the inverse is recovered at
  re-import. Disambiguates duplicate unit names with a short uuid
  suffix and logs a warning so round-trip fidelity is preserved even
  on legacy graphs with data-quality issues. Legacy GraphML sources
  whose PropertyNodes all carry the sentinel ``property_type =
  "string"`` are normalized: the actual qualia type comes from
  ``PN.name`` and the value from ``PN.description`` when
  ``PN.value`` is empty. Locked in by 4 round-trip scenarios in
  ``test_unified_xlsx_roundtrip.py`` covering the resolver
  fingerprint invariance, Combiner preservation, relation
  attribution preservation, and a real-data smoke test on the Great
  Temple graphml (102 units → export → re-import → 102 units).
- **Unified xlsx pipeline** (Phase B — DP-02 / DP-49). Single-file
  replacement for the legacy ``stratigraphy.xlsx`` + ``em_paradata.xlsx``
  two-step flow:
  - New template ``s3dgraphy/templates/em_data_template.xlsx`` with
    5 typed sheets: ``Units`` (skeleton), ``Epochs`` (swimlanes),
    ``Claims`` (long-table, one row per asserted fact), ``Authors``
    (normalized catalog with a ``KIND`` column distinguishing human
    authors from AI extractors), ``Documents`` (normalized catalog).
  - New importer ``s3dgraphy.importer.unified_xlsx_importer.UnifiedXLSXImporter``
    builds a complete graph from one xlsx in a single pass: author /
    document catalogs, epochs, stratigraphic units, and all claim
    rows (scalar qualia, temporal qualia, epoch membership via
    ``belongs_to_epoch``, and stratigraphic relations via
    ``is_after`` / ``overlies`` / ``cuts`` / ``fills`` / ``abuts`` /
    ``bonded_to`` / ``equals``). Each claim row carries its own
    attribution triple(s): ``EXTRACTOR_i`` / ``DOCUMENT_i`` /
    ``AUTHOR_i`` / ``AUTHOR_KIND_i``. Relational claims store the
    attribution on the edge's ``attributes`` dict; PropertyNode
    claims use the standard paradata chain.
  - Multi-source (Combiner) rows: when both
    ``EXTRACTOR_1`` / ``EXTRACTOR_2`` and ``COMBINER_REASONING`` are
    populated, a ``CombinerNode`` is inserted between the
    ``PropertyNode`` and the two ``ExtractorNode`` instances.
  - 6 synthetic test scenarios in ``test_unified_xlsx_importer.py``
    (catalog creation, relation attribution, SL_PD chronology
    override, author vs AI-extractor attribution, combiner structure,
    A.1 compaction invariance on xlsx-sourced graphs).
- **Diagnostics attribution now follows the ``has_data_provenance``
  chain** (xlsx pipeline). Previously ``attribute_property_node``
  walked only the ``is_in_paradata_nodegroup`` sibling-extractor
  path, which works for yEd-sourced graphs but misses the xlsx
  in-memory pattern (``PN → has_data_provenance → Extractor →
  has_author``, or through a ``CombinerNode``). The walk order is now:
  direct ``has_author`` → provenance chain (extractor / combiner) →
  paradata-group siblings. Unifies attribution coverage across import
  sources.
- **Chronology diagnostics with claim attribution** (DP-02 / DP-32
  Phase A.2). New module ``s3dgraphy.diagnostics`` providing:
  - ``attribute_property_node(graph, pn)`` and
    ``attribute_temporal_claim(graph, strat_node, temporal_type)`` —
    walk the paradata chain to find who made a specific claim. Resolution
    order: direct ``has_author`` on the PropertyNode → sibling
    ``ExtractorNode`` in the containing ParadataNodeGroup →
    ``has_author`` on that extractor. Returns ``(display_text, kind,
    author_uuid)`` where ``kind`` is ``"author"`` (transcribed from the
    PDF author; the claim is in the source) or ``"extractor"`` (derived
    by an AI tool like StratiMiner; the claim is new).
  - ``detect_stratigraphic_cycles(graph)`` — Tarjan SCC over the
    ``is_after`` / ``cuts`` / ``overlies`` / ``fills`` / ``is_before``
    edges, returning every loop (and self-loop) in the stratigraphic
    order. AI extractors occasionally close these loops; the BFS in
    ``_propagate_tpq_taq`` already survives them via a visited set but
    the user must be notified.
- **Paradox warnings now carry attribution**. The ``[chronology
  paradox]`` messages emitted by ``_propagate_tpq_taq`` include a
  trailing ``[attributed to <name> (<kind>)]`` suffix when the
  offending PropertyNode can be traced to an author or an extractor.
  This lets the user decide whether to audit the original document
  author or the AI extractor that produced the bad inference.
- **Stratigraphic cycle warnings emitted automatically**.
  ``Graph.calculate_chronology()`` now runs a cycle-detection pass
  before TPQ/TAQ propagation and appends one
  ``[stratigraphic cycle]`` warning per loop, with per-node
  attribution so the user can pinpoint the right extractor. Tests:
  9 scenarios in ``test_diagnostics.py`` covering human/AI
  attribution, sibling-extractor resolution, missing attribution,
  2- and 3-node cycles, linear chain (no false positives), end-to-end
  paradox warning with attribution.

- **Reverse-propagation compaction** (DP-32 / DP-49 Phase A.1). New module
  ``s3dgraphy.transforms.compact`` exposing three functions for pre-export
  metadata formalization:
  - ``prune_redundant_propagative_edges(graph)`` — removes per-node
    ``has_author`` / ``has_license`` / ``has_embargo`` edges and
    ``has_property`` edges to temporal PropertyNodes when the
    swimlane-level resolver returns the same value anyway.
  - ``hoist_propagative_metadata(graph)`` — when every stratigraphic
    unit whose primary swimlane is Epoch E declares the same single
    target for ``has_author`` / ``has_license`` / ``has_embargo``, promotes
    the declaration to an SL_PD anchored to E (created if missing) and
    removes the per-unit edges. Chronology is pruned but never hoisted
    (PropertyNode deduplication is out of scope).
  - ``compact_propagative_metadata(graph)`` — runs hoist then prune.
  Both passes preserve the resolver output for every node (lossless
  reformulation). Conservative rules: no hoist on partial overlap, no
  hoist on divergent targets, no hoist on multi-epoch nodes
  (``survive_in_epoch``). Locked in by 8 synthetic scenarios in
  ``test_compact_metadata.py`` including idempotence of
  ``compact_propagative_metadata``.
- **Dashed-connector reclassification** (DP-51). The yEd palette has no
  dedicated connector style for ``has_author`` / ``has_license`` /
  ``has_embargo``. The importer's ``enhance_edge_type`` now inspects the
  target class of a ``has_data_provenance`` edge (the dashed connector's
  default semantic): ``AuthorNode`` / ``AuthorAINode`` → ``has_author``,
  ``LicenseNode`` → ``has_license``, ``EmbargoNode`` → ``has_embargo``.
  Covers legacy EM graphs that connect strat units directly to paradata
  image nodes with a generic dashed edge.

### Refined

- **EpochNode queries report [swimlane], never [node]**. When the resolver
  is invoked directly on an EpochNode, node-level and swimlane-level
  collapse to the same lookup (the Epoch IS the swimlane). The generic
  resolver now skips the node-level call for Epoch inputs and always
  tags the result ``"swimlane"`` (or ``"graph"`` for canvas-header
  fallbacks). Matches the Epoch Manager UI mental model where values
  shown on an epoch come from the swimlane-level Paradata Node Group.
- **SL_PD auto-edge supports top-level layout** (DP-19). The paradata
  auto-edge inference previously required the SL_PD group to be XML-
  nested inside an EpochNode's swimlane column. Now also supported: an
  SL_PD that sits at the canvas top level and draws an explicit
  ``has_first_epoch`` edge to the target Epoch, with its children
  connected via ``is_in_paradata_nodegroup``. Resolution order for the
  containing group: immediate XML parent → ``is_in_paradata_nodegroup``
  edge. Resolution order for the anchor: first non-ParadataNodeGroup XML
  ancestor → ``has_first_epoch`` outgoing from the group. The pass is
  now scheduled **after** ``connect_nodes_to_epochs`` so that a
  Y-position-derived ``has_first_epoch`` from the SL_PD is available.
- **Swimlane chronology honours SL_PD PropertyNodes**. The
  ``absolute_time_start`` / ``absolute_time_end`` rules' swimlane
  getters (``_epoch_start`` / ``_epoch_end``) now prefer a PropertyNode
  attached to the Epoch (typically auto-edged from an SL_PD) over the
  header ``epoch.start_time`` / ``end_time`` declared in the yEd
  swimlane title. A stratigraphic unit in that epoch therefore inherits
  the refined window when a PropertyNode is declared in the
  swimlane-level paradata group. The ``[chronology mismatch]`` warning
  still surfaces header/PN disagreements so the user can reconcile yEd.

### Changed

- **Dropped legacy ``absolute_start_date`` / ``absolute_end_date``
  aliases** across the codebase. The canonical (and sole) pair of
  chronology qualia is now ``absolute_time_start`` /
  ``absolute_time_end``. Consumers updated: the EM-blender-tools
  PropertyGroup fields (``em_base_props.py``, ``document_manager/data.py``,
  ``document_manager/ui.py``, ``paradata_manager/ui.py``,
  ``populate_lists.py``), the s3dgraphy core-concepts and operators-guide
  docs, and the current AI extraction prompt (v4). Existing GraphML
  sources with the old names must be migrated manually. Archived AI
  prompts v2/v3 are left as-is.

### Refined

- **EpochNode resolves as its own swimlane** (DP-32 Priority 4). Passing an
  ``EpochNode`` directly to ``resolve`` / ``get_property`` now yields the
  expected swimlane-level value instead of ``None``. The swimlane iterator
  in ``resolvers.property_resolver`` short-circuits to ``[epoch]`` when the
  input is itself an EpochNode, so chronology (``absolute_time_start`` /
  ``absolute_time_end``), ``author``, ``license`` and ``embargo`` are all
  reachable on epochs without a dedicated code path in every consumer. The
  Epoch Manager UI's ``epoch.start_time``/``end_time`` workaround is no
  longer needed. Strat-unit resolution is unchanged. Locked in by a new
  scenario in ``test_chronology_resolver.py`` (10 scenarios total).
- **Multi-author resolution**. ``AUTHOR_RULE`` at node- and swimlane-
  level now follows *every* ``has_author`` edge, not just the first one,
  and joins the display values with ``" ; "``. Duplicate display strings
  are deduplicated while preserving edge order.
- **Author display uses the description field**. The 1.5 dev9 yEd
  palette convention is ``AuthorNode.name = "A.01"`` (short code) and
  ``AuthorNode.description = "Giulia Rossi, ORCID:…"`` (human content).
  ``_format_author`` now prefers the description; falls back to
  ``data["name"] + data["surname"]``; last resort is the code in
  ``node.name``.
- **Description marker stripped at import**. The ``_s3d_node_type:<X>``
  round-trip marker is scrubbed from the description when the importer
  creates Author/AuthorAI/License/Embargo nodes, so panels never leak
  the technical marker into the UI.
- **Import-time warning for epoch chronology mismatch**. After auto-
  edging the paradata groups, the importer checks every EpochNode for a
  conflict between the swimlane-header times (``epoch.start_time`` /
  ``epoch.end_time``) and a PropertyNode declared inside an SL_PD.
  When they disagree, a ``[chronology mismatch]`` warning is pushed to
  ``graph.warnings`` so the user can reconcile the source in yEd. The
  resolver already preferred the PropertyNode; this surfaces the
  inconsistency instead of silently hiding it.

### Added

- **GraphML export of paradata image nodes** (AuthorNode, AuthorAINode,
  LicenseNode, EmbargoNode).
  - New module ``exporter/graphml/palette_resources.py`` parses
    ``templates/em_palette_template.graphml`` once at import time and
    exposes, per paradata node class, the label prefix, the refid used in
    the palette, and the verbatim ``<y:Resource>`` payload. Changing an
    icon in yEd requires **no Python change** — just re-save the palette
    template.
  - New generator ``exporter/graphml/paradata_image_generator.py``
    (``ParadataImageNodeGenerator``) emits the four ``<node>`` XML
    elements with a correct ``<y:ImageNode>`` + label prefix + refid, and
    adds an explicit ``_s3d_node_type:<NodeType>`` marker in the node
    description for bulletproof round-trip.
  - ``GraphMLPatcher`` now dispatches AuthorNode / AuthorAINode /
    LicenseNode / EmbargoNode to the new generator when patching an
    existing file. If the destination file already contains an
    ImageNode whose label prefix matches, its refid is reused; otherwise
    the matching ``<y:Resource>`` is injected from the palette template
    into the file's ``<y:Resources>`` block under a fresh refid.
  - Round-trip smoke test ``test_paradata_image_roundtrip.py``:
    generates a minimal GraphML from scratch containing one of each of
    the 4 paradata image nodes (resources embedded from the palette),
    re-imports it, and verifies the 4 classes come back intact.

### Changed

- **Unified naming to ``absolute_time_start`` / ``absolute_time_end``**
  (EM qualia standard). The rename touches:
  - ``resolvers.builtin_rules``: the two temporal PropagationRules now
    carry ids ``absolute_time_start`` / ``absolute_time_end`` (previously
    ``chronology_start`` / ``chronology_end``). Consumer code that called
    ``Graph.get_property(node, "chronology_start")`` must use the new
    id. Internal attributes ``CALCUL_START_T`` / ``CALCUL_END_T`` on
    resolved nodes are unchanged.
  - Node-level seed detection: the temporal PropertyNode is now matched
    on name/type ``absolute_time_start`` / ``absolute_time_end``
    (previously ``absolute_start_date`` / ``absolute_end_date``).
  - ``JSON_config/em_qualia_types.json``: temporal qualia entries
    renamed to match.
  - Warnings emitted by the paradox detector and the companion test
    suite updated.

### Refined

- **Auto-edge inference is now scoped to FREE paradata groups** (those
  with no incoming ``has_paradata_nodegroup`` edge AND whose name
  starts with the ``SL_`` prefix by EM convention). This prevents the
  importer from double-wiring the DP-43 node-level paradata groups
  (``USV104_PD``, ``SU001_PD``, …) which are already handled by the
  pre-existing ``Graph.connect_paradatagroup_propertynode_to_stratigraphic``
  pathway.
- **Auto-edge now also covers PropertyNode** (``has_property``) in
  addition to the four paradata image nodes (Author / AuthorAI /
  License / Embargo). A PropertyNode called ``absolute_time_start``
  placed inside a swimlane-level SL_PD is therefore automatically
  connected to the enclosing EpochNode, which means the DP-32
  chronology resolver sees it as a node-level seed without the author
  having to draw the edge explicitly in yEd.
- **Hash-based paradata icon detection removed.** Palette PNGs may be
  redrawn or re-exported between versions (and each yEd save can
  perturb the base64 payload); the stable convention is the label
  prefix (same strategy already used for ``D.`` / ``C.``). Detection
  order is now: explicit ``_s3d_node_type:`` marker → ``<y:ImageNode>``
  + known label prefix. ``em_palette_icons.json`` shrinks to just the
  ``label_prefixes`` map.

### Added

- **Auto-inference of ``has_author`` / ``has_license`` / ``has_embargo``
  edges from ParadataNodeGroup membership** (DP-19 / DP-43 groundwork).
  After parsing a GraphML file, the importer runs a post-processing pass
  that, for every ``AuthorNode`` / ``AuthorAINode`` / ``LicenseNode`` /
  ``EmbargoNode`` found, walks the XML parent chain upward and emits the
  corresponding edge from the **nearest graph-visible non-
  ParadataNodeGroup ancestor**. Concretely:
  - An Author/License/Embargo node inside a swimlane-level
    ParadataNodeGroup (SL_PD) attached to a ``EpochNode`` → edge from
    the ``EpochNode`` (swimlane-level resolver now active).
  - An Author/License/Embargo node inside a node-level
    ParadataNodeGroup (DP-43 ``US_01_PD``, ``USV104_PD``, …) nested in
    a stratigraphic unit → edge from the stratigraphic unit
    (node-level resolver now active).
  - An Author/License/Embargo node inside a canvas-level group (parent
    is the top-level graph, not a node) → no edge created; the value
    is already reachable via the DP-40 canvas-header attributes on
    ``graph.attributes["author_name"|"license"|"embargo"]``.

  The inference never overwrites existing edges (duplicate-safe) and
  adds a ``[paradata auto-edge]`` warning summarizing how many edges
  were inferred.
- **Paradata image nodes wired into the GraphML importer** (DP-51
  groundwork). The importer now detects and instantiates the four
  palette-based paradata nodes:
  - ``AuthorNode`` — label prefix ``A.`` (human author)
  - ``AuthorAINode`` — label prefix ``AI.`` (AI-assisted author, new
    subclass of ``AuthorNode``)
  - ``LicenseNode`` — label prefix ``LI.``
  - ``EmbargoNode`` — label prefix ``EB.``

  Detection is **multi-signal** with a Hard > Medium > Weak priority
  chain, matching the pattern used for ``EM_check_node_continuity``:

  1. Explicit ``_s3d_node_type:<NodeType>`` marker in the node's
     description or URL field (round-trip aid).
  2. ``<y:ImageNode>`` + ``<y:Image refid="N"/>`` where the resource's
     SHA-256[:16] (post XML-entity-decoding, whitespace stripped) matches
     an entry in ``JSON_config/em_palette_icons.json``. This is robust
     to label renames and typos.
  3. ``<y:ImageNode>`` + label prefix match (``AI.``/``A.``/``LI.``/``EB.``
     checked longest-first to avoid ``AI.`` being shadowed by ``A.``).

  The dispatcher kicks in just before the generic fallback node path so
  existing stratigraphic / property / extractor / combiner / continuity
  detection is unchanged.
- **``em_palette_icons.json``** — new configuration file indexing the
  stable SHA-256[:16] of each palette icon to the node type it
  represents. Adding a new palette icon is a JSON edit, no Python change.
- **``AuthorAINode`` subclass** of ``AuthorNode`` (``node_type =
  "author_ai"``) with ``model`` and ``prompt_reference`` fields. Because
  it inherits from ``AuthorNode``, all consumer code that uses
  ``isinstance(n, AuthorNode)`` keeps working.
- **Two new built-in propagation rules** in
  ``resolvers.builtin_rules``:
  - ``LICENSE_RULE`` — follows ``has_license`` edges at node/swimlane
    levels, falls back to ``graph.attributes["license"]`` at canvas
    level.
  - ``EMBARGO_RULE`` — follows ``has_embargo`` edges; graph-level
    fallback to ``graph.attributes["embargo"]``.
  - ``AUTHOR_RULE`` node-level and swimlane-level getters are now
    active: they follow ``has_author`` edges to
    ``AuthorNode``/``AuthorAINode`` instances and format the returned
    value as ``"Name Surname"``. Canvas-header fallback via
    ``author_name`` / ``author_surname`` is unchanged.

### Changed

- ``has_author`` connections datamodel entry now lists
  ``AuthorAINode`` as an explicit target and adds ``EpochNode`` to the
  allowed source list so the swimlane-level resolver can attach an
  author directly to an epoch.
- ``has_embargo`` connections datamodel entry: source widened from
  ``["LicenseNode"]`` to ``["Node", "GraphNode", "LicenseNode"]``. Now
  mirrors ``has_license`` so an embargo can be attached to the canvas,
  a license, or any node directly. Also aligns with the declared
  intent: "si possono usare collegati ad ogni tipo di nodo".

### Tests

- Extended ``test_chronology_resolver.py`` with two new scenarios:
  - ``run_license_embargo_rule_test``: graph-level (canvas header)
    fallback for license and embargo via ``Graph.get_property(..., "license")``
    and ``get_property(..., "embargo")``.
  - ``run_author_via_has_author_edge_test``: a node with its own
    ``has_author`` → ``AuthorNode`` overrides the graph-level canvas
    header author.
- Ad-hoc round-trip smoke test against
  ``TempluMare_EM_converted_converted 2.graphml``: the four SL_PD
  paradata nodes are parsed to the correct classes via the hash signal
  (strongest), without relying on the label prefix fallback.
- New synthetic test ``run_paradata_auto_edge_test``: builds a minimal
  GraphML with a ParadataNodeGroup (``#FFCC99`` background) nested
  inside a stratigraphic unit, containing an AuthorNode tagged with
  the explicit ``_s3d_node_type:AuthorNode`` marker. Verifies that the
  importer (a) detects the AuthorNode, (b) auto-infers the
  ``has_author`` edge from the US to the AuthorNode, and (c) the
  resolver then returns the author when ``get_property`` is called on
  the US.

### Added (earlier in this release)

- **Generic propagative property resolver** (`s3dgraphy.resolvers`, DP-32
  Layer A). New subpackage that formalizes the 3-level hierarchical
  resolution **node > swimlane > graph** used across the Extended Matrix
  metadata system.
  - `PropagationRule` dataclass describing how to look up a property at each
    level (`node_getter`, `swimlane_getter`, `graph_getter`, optional
    `swimlane_aggregate`).
  - `resolve(graph, node, rule, default=None)` and
    `resolve_with_source(...)` — walk the three levels and return the first
    non-null value (or the value plus the level it came from).
  - Registry: `register_rule`, `unregister_rule`, `get_rule`, `list_rules`.
  - Built-in rules registered on import (`resolvers.builtin_rules`):
    - `chronology_start` and `chronology_end` — reproduce the previous
      hardcoded seed logic exactly (verified by regression test).
    - `author` — graph-level fallback already active (reads Canvas Header
      `author_name` / `author_surname` from DP-40). Node-level and
      swimlane-level getters are stubs for DP-51 (AuthorNode in yEd) and
      DP-19 (Swimlane Paradata Node Group); both honor an explicit
      `attributes["author"]` override if an importer sets one.
- **`Graph.get_property(node, rule_id, default=None)`** — one-line
  convenience wrapper for consumers that want to resolve a registered
  property by id.
- **Coherence / paradox detection in chronology closure** (DP-32 Layer B,
  Hard policy). When the TPQ/TAQ propagation would overwrite a
  user-declared `absolute_start_date` / `absolute_end_date` seed with a
  stratigraphically-inconsistent value, the propagation is blocked at the
  conflicting node, the declared value is preserved, and a descriptive
  warning is appended to `graph.warnings`. BFS does not traverse through
  the conflicting node (Hard policy). Seeds that merely tighten derived
  (swimlane-fallback) values remain silent as before — only true paradoxes
  are flagged.

### Changed

- **`Graph._calculate_base_chronology`** is now a thin wrapper around
  `resolve(...)` using the built-in `chronology_start` and `chronology_end`
  rules. External behavior is unchanged (locked by the regression test in
  `test_chronology_resolver.py`).

### Tests

- New synthetic regression suite in the repo root
  (`test_chronology_resolver.py`) covering:
  1. Baseline chronology (node PropertyNode seed, swimlane fallback,
     `survive_in_epoch` extension, simple TPQ across `is_after`).
  2. TAQ reverse propagation (recent node's `absolute_end_date` tightens
     older nodes).
  3. Overlapping constraints (chain with both a start seed and a later end
     seed split the population into three coherent sub-ranges).
  4. Paradox detection (conflicting node-level seeds preserved, warning
     raised).
  5. `AUTHOR_RULE` cascade (node override > swimlane attribute > graph
     canvas header).
