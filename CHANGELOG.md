# Changelog

All notable changes to **s3dgraphy** are documented here.

## [Unreleased]

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
