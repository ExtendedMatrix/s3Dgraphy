# Source of truth

*Decided by E.D. on 2026-09-27. Measured on connections datamodel 1.6.20,
node datamodel 1.6.8, qualia 1.6.1.*

s3Dgraphy has one rule for names: **the datamodel is asked, not repeated.** A
node type, an edge type, its direction, its spellings and its projection are
declared once, in a JSON file under `src/s3dgraphy/JSON_config/`. Everything
else reads them from there.

There are four levels, and the arrow points one way: from the top down.

## 1 · The datamodel JSON — the source of truth

| File | What it declares |
| --- | --- |
| `JSON_config/s3Dgraphy_connections_datamodel.json` | every edge type: name, label, `reverse`, `spelling_of`, `allowed_connections`, the CIDOC / extension `mapping`, `deprecated` |
| `JSON_config/s3Dgraphy_node_datamodel.json` | every node type, by family: class, abbreviation, `parent`, CIDOC `mapping`, `em_extension` |
| `JSON_config/em_qualia_types.json` | the qualia (property types) and their projections |
| `JSON_config/datamodel_translations.json` | localised descriptions, keyed per class; English is the source |

Loaded through `edges/connections_loader.py` (`get_connections_datamodel()`)
and the node-datamodel readers.

### Glyphs: the SVG is authored, the JSON is distributed

*Decided by E.D. on 2026-09-28 (em_visual_rules 1.6.18).*

One piece of level 1 has a file **above** it: the pictograms. The nodes the 2D
scene draws as a glyph (`2d_render_glyph_types`, and the DTC glyphs of
`dtc_kinds`) carry their drawing inside `em_visual_rules.json` as vector paths,
in the block `2d_glyphs`. That block is the **distributed truth** — what every
consumer reads, and the only form of the drawing it may rely on. But nobody
writes it: it is generated from the **authored source**, an SVG in
`JSON_config/src/2D/` (`src/2D/dtc/` for DTC, `src/2D/bozze/` for a draft
awaiting approval).

| To | Do |
| --- | --- |
| redraw a glyph | edit its SVG, then `python -m s3dgraphy.tools.glyphs_from_svg --write` |
| check nothing drifted | `python -m s3dgraphy.tools.glyphs_from_svg --check` (exit 1 on drift) |
| approve a draft | move it from `src/2D/bozze/` to `src/2D/` (a DTC draft `bozze/dtc_<glyph>.svg` to `src/2D/dtc/<glyph>.svg`), remove its `BOZZA` comment, `--write` |
| look before approving | `python -m s3dgraphy.tools.glyph_sheet OUT.html` |

`tests/test_glyph_paths.py` fails the moment the SVG and the block disagree, so
an edit on either side alone does not survive the suite. How a consumer draws an
entry is in [Drawing a glyph](drawing-a-glyph.md).

## 2 · `em.ttl` — the ontology, aligned by hand to level 1

`JSON_config/em.ttl` is the companion ontology (namespace `em:`, «CRMem»). It
is aligned **with care** to the datamodel: every `em:` term a datamodel cites
has its declaration in `em.ttl`, and each declaration says in its comment
(`Maps to: …`) which datamodel entries it serves.

Measured 2026-09-27: the three datamodels cite 61 `em:` terms and all 61 are
declared (none missing). `em.ttl` declares 86; the 25 not cited by a datamodel
are projected by code directly (the editorial stamps, the CRDT tombstones, and
the six physical sub-properties `em:overlies … em:physicallyEquals`, which the
RDF exporter reaches through its own `AP11_SUBPROPS` table — see the census in
the report of 2026-10-19).

## 3 · The code — derived from 1 and 2

Python nodes and edges, importers and exporters, inference, merge, GraphML,
sync. **No list of names written by hand where the datamodel can be queried.**

The connections loader is the one door:

| Question | Ask |
| --- | --- |
| is this an edge type at all? | `edge_exists(name)` |
| its reverse / is it one? | `get_reverse_name(name)`, `is_canonical(name)` |
| directionless? | `is_symmetric(name)` |
| the name to WRITE | `normalize_edge_name(name)` (reverse → canonical, older spelling → canonical) |
| every name to RECOGNISE | `spellings(name)` |
| who may be joined | `get_allowed_sources/targets(name)` |

**Writers write the canonical name. Readers accept every name the datamodel
accepts.** A reader that needs a second name asks `spellings()`; a writer that
needs to pick asks `normalize_edge_name()`. Neither keeps its own list.

### Older spellings (`spelling_of`)

An edge entry may carry `spelling_of: <canonical>`: the same relation under an
older name. Same RDF projection, **accepted when read, never written**. Today:
`is_bonded_to` → `bonded_to`, `is_physically_equal_to` → `equals`. It is
**not** `deprecated`, which drops an edge from RDF on export and import. The
loader refuses a `spelling_of` that names a missing entry, another spelling, or
a relation whose direction differs from its own.

### Known exceptions

Censused on 2026-09-27, **not repaired**: about 60 hand-written lists of edge
names in 30 files and about 55 of node-type names in 25 files. The largest
clusters:

| Cluster | Copies | Derivable today? |
| --- | --- | --- |
| physical-relation sets (`overlies` … `equals`) | 8 (rapporti, graph_merger, graphml_exporter ×2, import_graphml, both xlsx modules, graphml_writer) | yes — edges with a `mapping.type_tag`, closed under `reverse` and `spelling_of` |
| stratigraphic abbreviation lists (`US`, `USVs`, …) | ~10 | yes — `classification.ALL_US_TYPES`, itself read off the node datamodel |
| «source is more recent» tables | 3 (graph.py, diagnostics.py, temporal/inference_engine.py) | **no** — the datamodel has no temporal-direction field |
| yEd line-style tables | 2, and they disagree (graphml_patcher, edge_generator) | **no** — `em_visual_rules.json` lacks the physical relations |
| `em:` sub-property per physical relation | 1 (`rdf_exporter.AP11_SUBPROPS`) | **no** — no `mapping.em_subproperty` field |
| pyArchInit labels and `unita_tipo` codes | several in `sync/` | **no** — level-4 vocabulary, belongs in a mapping file |

So the lists split into two kinds. Some could already be derived and just have
not been yet. The others encode something the datamodel does not say. For
those, the fix is a new field, and until it exists the list is the declaration.

One inversion is open and named: `node_registry.generated.json` is generated
**from** the Python node classes (`tools/sync_node_datamodel.py`), so for the
class hierarchy (`parent`, runtime `node_type`) the arrow today runs from code
to JSON. The hand-written node datamodel also declares `parent` for 54 classes,
and 5 of them disagree with the classes (measured 2026-09-27: USVs, USVn → the
datamodel says `StratigraphicNode`, the code `VirtualStratigraphicUnit`; the
three RepresentationModel* → `Node` vs `RepresentationNode`). No test compares
the two.

## 4 · The mapping files — dialogue with other datamodels

`src/s3dgraphy/mappings/` (pyArchInit, EMdb, xlsx, source lists…) and
`JSON_config/acquisition_mappings/`. They translate **someone else's**
vocabulary into level 1. That translation lives there, in data, not in the
code. A mapping carries a `_validated_against` stamp naming the datamodel
versions it was checked against.

The pyArchInit `rapporti` labels (ten relations × ten UI languages) are still
a table in `sync/rapporti.py`; moving them to a mapping file is proposed in the
report of 2026-10-19, not done.

What happens after level 4, when the change leaves this repository for the
tools, is in [Datamodel propagation](DATAMODEL_PROPAGATION.md).

## Language of literals

Decided by E.D. on 2026-09-28. A text in a natural language leaves in RDF with
its language tag (`"strato di crollo"@it`); everything else leaves as before.

- **The marker.** Which properties are text is said by the datamodel, not by
  the exporter: `"natural_language": true` on `Node.properties.description`
  (inherited by every node type) and on the quale `narrative_content`. A
  `data_type: string` is not enough: `inventory_number` is a string and a code.
  One function reads the marker, `_Datamodel.is_natural_language`.
- **The cascade.** The node's `data.lang` (the field the narrative node already
  had, DP-63) → the study's working language (`GraphNode.data.language`,
  emitted as `dcterms:language` on the graph) → none.
- **`und` is not silence.** A language never declared leaves untagged and is
  counted (`literals_untagged`); `data.lang: "und"` is a language declared
  unknown and leaves as `@und`. The language is never guessed from the text.
  Tags are checked (simple BCP 47) where they are written; an invalid one is
  refused and nothing is stored.
- **Names are invariant.** `name` is never tagged: `US 3014`, `W5023`,
  `USM5023` are identities, even when their initials come from a language.
- **Translations are nodes** (E.D., 2026-10-01, «Le traduzioni»). The original
  stays a string in its field, in the language it was written in: it is
  testimony, and `update_field` / last-writer-wins per field stay as they are.
  Each translation is a `TranslationNode` (`crm:E33_Linguistic_Object`) reached
  by `has_translation` (`crm:P73_has_translation`), with its languages of
  arrival and departure, the field, the method (`manual` | `ai` | `edition`) and
  the sha256 of the original it translated — never a second value of the same
  field. `api.to_review` lists what waits for a person: `ai`,
  `review_requested`, `stale`.
- **The original is marked in RDF.** A node's own `data.lang` leaves as
  `em:originalLanguage`, equal to the study's or not; each aligned translation
  adds a literal on the same predicate with its own tag, and leaves as its own
  resource (`prov:wasDerivedFrom`, `prov:wasAttributedTo`). em.json → TTL →
  em.json gives `data.lang` back exactly where it was.
- SKOS concepts do not change: their label resolves at reading.

## The rule, in one line

> If the datamodel can answer, ask it. If it cannot, the fix is a field in the
> datamodel — not a list in the code.
