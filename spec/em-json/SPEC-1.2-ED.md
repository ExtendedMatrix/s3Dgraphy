# em.json — the Extended Matrix document format

**Version 1.2 · Editor's Draft · 30 October 2026**

| | |
|---|---|
| This version | Editor's Draft, `spec/em-json/SPEC-1.2-ED.md` (not published) |
| Latest release | 1.1, <https://w3id.org/extendedmatrix/spec/em-json/> |
| Schema | <https://w3id.org/extendedmatrix/schemas/em.v1.1.schema.json> |
| Previous schema (1.0, flat form) | <https://w3id.org/extendedmatrix/schemas/em.v1.schema.json> |
| Editor | Emanuel Demetrescu (CNR-ISPC), ORCID [0000-0002-5065-7970](https://orcid.org/0000-0002-5065-7970) |
| Source | `spec/em-json/` in the [s3Dgraphy](https://github.com/ExtendedMatrix/s3Dgraphy) repository |
| Licence | Text: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Schemas and examples: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |
| Status | **Editor's Draft.** 1.2 is a minor, ADDITIVE version: it describes the site, its footprint and the GIS layers (§2.5). No key of the container changes, the schema of 1.1 validates its files and a reader of 1.1 reads them; writers keep writing `"1.1"` until the editor makes 1.2 a Release. The Release is the editor's decision. |

## 1. What it is for

An em.json file holds the work of an Extended Matrix study: the stratigraphic
units and their relations in time, the sources and the reasoning behind every
reconstruction (the *paradata*), the 3D models and documents they refer to, and
how the whole is drawn.

Four things are distinct, and the rest of this document depends on keeping
them apart:

- **Extended Matrix** is a formal language. It represents the concepts of a
  stratigraphic and reconstructive reading with a layout, a logic of the flow
  of time and graphic elements of its own, and it rests on precise algorithms
  that propagate information between portions of the graph, following the
  principles of virtual historical reconstruction.
- **The content of a Matrix** is formalized as a **property graph**, mapped
  deterministically onto a triplestore.
- **em.json** is the **container** of that property graph. This document
  specifies it.
- **s3Dgraphy** is the library through which the tools read and write it.

The tools read and write the same file, each with its own metaphor for the
content: EM Tools for Blender, EMStudio, Heriverse, StratiField and its field
chatbot, and the StratiGraph server, where several people work on it together
in shared rooms.

It is the point where these tools meet. That is why it is specified here, in a
document separate from any one program: whoever reads and writes em.json can
work with all of them.

The file is JSON (RFC 8259), UTF-8. The extension is `.em.json`; `.emj` is
read as the same thing.

## 2. The model

### 2.1 A container of graphs

An em.json file is always a **container**: a header and one or more **graphs**.

- A **study graph** is one Extended Matrix: the units of a site, a trench, a
  building, with their epochs and their paradata. A project with several
  saggi, or several readings of the same site, has several study graphs.
- Three **special members** are graphs too, recognised by a marker in their
  data (`data.em_collection`), never by their name:
  - the **shelf** (`ShelfGraph`): what the study shares — authors, licences,
    documents used by more than one graph;
  - the **documentation** (`DTCCorpus`): how the digital objects were made —
    acquisitions, transformations and the resources they are about;
  - the **periodizations** (`Periodizations`): the shared measures of time —
    each periodization with its horizons (a label, a start, an end, a colour).
    A unit is «inside» a horizon when their intervals overlap.

A node that belongs to several graphs keeps one identifier everywhere, so two
containers can be merged by identifier, without a server.

A relation between a unit of one graph and a unit of another is a **link**,
kept in the graph of its source and addressed as «graph → node».

### 2.2 Nodes

A node has an **identifier**, a **type** and, optionally, a **name**, a
**description** and its **data** (the fields its type declares).

A property writes its value in both places: `description` (where EM has always
kept it, and where older readers look) and `data.value`, which mirrors it. Two
exceptions: the `geometry` property, whose `data.value` is the identifier of its
shape, and any `data.value` that is a bare identifier pointing at a node.

The types and their fields are not listed in this specification. They belong to
the **EM datamodel** — the node datamodel, the connections datamodel and the
qualia vocabulary — which evolves on its own rhythm and is mapped to CIDOC CRM
and its extensions. Among them is CRMem, the extension of the CIDOC family that
declares the concepts of argued reconstruction absent from the other models: in
this chain it is a target of the mapping, not the datamodel itself. Every file says which versions of the datamodel it follows.
This keeps the format stable while the vocabulary grows.

### 2.3 Edges

An edge has an **identifier**, a **type** (the relation, as the connections
datamodel names it), a **source** and a **target** (two nodes of the same
graph), and optionally **attributes**: facts about the edge itself. The one
every reader should know is `origin` on the edges of relative chronology —
`derived` (computed from the physical relations), `user` (written by a person),
`imported` (read from another software's file).

The physical relations carry their meaning in time, declared in the
connections datamodel: *cuts*, *fills*, *overlies* say that one unit is later
than the other; *abuts*, *is bonded to*, *equals* say that the two are
contemporary.

### 2.4 Paradata

The reasoning is part of the graph, not a note beside it. A property of a unit
(its height, its function, its date) is a node; the extractor that read it from
a source, the combiner that put several extractors together, the document it
comes from are nodes too, joined by edges. A reader that understands the
datamodel can follow any reconstruction back to its sources; a reader that does
not still has every node and edge.

The chain is always explicit: property → extractor (`has_data_provenance`) →
document (`extracted_from`). A property linked straight to a document
(`has_documentation`, from older files) is read and kept, but no tool writes it.

### 2.5 Georeferencing

A graph is placed in the world by its **geo-position** node: the coordinate
reference system (an EPSG code) and the shift that brings the local coordinates
of the 3D scene to it. How a single model was registered (control points, the
transform) is carried by nodes of the datamodel as well. External 3D models,
images and documents are **resources**, referenced by address and digest, never
embedded.

*Added in 1.2 (Editor's Draft).* **The site, its footprint, its GIS layers.**
Everything that enters a study follows the same three steps, a 3D model or a
GIS layer alike: the file becomes a **resource** (with its digest, stamped by
the digital-twin chain), the resource has its **frame**, a **node** of the
graph represents it.

- **The site** is a place: a location node of kind `toponym` and level `sito`,
  the last ring of the chain of names (nation, region, municipality, site),
  which the study of the graph took place at. A site supposed and not
  excavated is the same node with `virtual: true` (an `em:VirtualSite` in RDF).
- **Its footprint** is a property of the site whose value is a geometry in the
  GeoSPARQL WKT form, with its reference system INSIDE the value, so that the
  numbers cannot travel without their frame:

  ```json
  {"id": "fp1", "node_type": "property", "name": "footprint",
   "data": {"property_type": "footprint",
            "value": "<http://www.opengis.net/def/crs/EPSG/0/3844> POLYGON Z ((327337.82 448685.77 491.19, …))"}}
  ```

  `POLYGON` or `MULTIPOLYGON`, in 2D or with Z; at most 500 vertices in the
  value, above which the geometry is a layer. GeoJSON is not used for this:
  RFC 7946 admits WGS 84 only. Being a property, the footprint has its
  paradata like every other value: the extractor that computed it and what it
  was computed from (the proxies of the units it encloses, a plan, a layer).
- **A GIS layer** is a resource of type `gis_layer`, referenced and never
  embedded: `gis_format` (`shapefile`, `geopackage`, `geotiff`, `geojson`,
  `wms`, `wfs`, `ogc_api_features`), the `crs` the layer itself declares, its
  `bbox` in that CRS, the attribute that names a feature (`feature_key`) and,
  for a layer of points in 2D whose heights are an attribute, `z_field`. A
  shapefile is a set of files (`packaging: file_set`): the `.shp` and its
  companions, each with its digest. The site refers to its layers with
  `has_linked_resource`.
- **The frame of a layer** is the frame of a file (`data.frame`: a CRS and the
  shift its coordinates are net of). A layer in the CRS of the graph, or in a
  code of the same grid (EPSG:31700, deprecated, and EPSG:3844 are the same
  Stereo 70 grid), overlays the scene directly; a layer in another grid needs a
  reprojection, which a reader does not assume.

All of this is content of nodes and edges described by the datamodel (nodes
1.6.39, connections 1.6.50, qualia 1.6.10): a reader that does not know these
types or keys keeps them (§3.1).

### 2.6 Layout

How a graph is drawn — the position of each node, the rows of the epochs, the
folded groups, the bends of the lines — is optional and can always be computed
again. Each graph keeps its own layout. The file also carries a copy of the
active graph's layout at the top level, for readers that know only one.

### 2.7 Header and version of the work

The header says what the file is (`format`, `version`, `schema_version`), who
wrote it (`generator`, `last_editor`), which datamodel and ontology versions it
follows, and may carry the study's `title`, `description`, `visibility` and,
for a landscape, the `composition` (the studies it cites). A separate top-level
`version` counts the revisions of the *work* (not of the format).

**Profiles (optional).** A file whose content uses the types or the
vocabularies of a community profile declares it in `header.profiles`, a list
of `{"iri": …, "version": …}` — the identity of each profile and the version
the file was written with:

```json
"profiles": [{"iri": "https://example.org/em-profiles/example-toolmarks", "version": "0.1.0"}]
```

The key is additive: a reader that does not know it ignores it (§3.1), a
reader that knows it may say which profiles it lacks, and a missing profile
is never a reason to refuse a file. A profile has its own version, independent
of `header.version` and of the datamodel versions (§5). What a profile
contains, and how a node or an edge of a profile type carries what a reader
without the profile needs to draw it as the core type it specialises, is in
the [EM Profiles specification](https://github.com/ExtendedMatrix/vocabularies/blob/main/profiles/SPEC.md).

## 3. Reading

A conforming reader:

1. **Ignores what it does not know.** A key it does not know, at any level, is
   skipped without error. A node of an unknown type is kept as a generic node
   that keeps its type, so that writing the file back does not erase it; an edge
   of an unknown type, or touching a node of an unknown type, is kept as it is;
   a special member with an unknown marker is read as an ordinary graph.
2. **Refuses only an unknown major version.** `header.version` is read as
   `major.minor`; a reader refuses a major it does not know and reads every minor
   of its own. `schema_version` is never a reason to refuse a file.
3. **Reads the flat form of 1.0.** A file with a single `graph` instead of
   `graphs` is a container of one graph.
4. **Treats `null` as absent**, and an empty text as no text.
5. **Recognises a special member by its marker**, never by its member id.
6. **Uses the member's own layout** when there is one; otherwise the top-level
   layout goes to the graph whose nodes it positions, else to the active graph.
7. **Reports a broken reference** (a link to a missing graph, an
   `active_graph_id` that is not a member) and goes on reading.

## 4. Writing

A conforming writer:

1. Writes the **container** form, even for one graph.
2. Writes `header.format` (`"em.json"`), `header.version` (`"1.1"` for this
   specification), `header.schema_version`, `header.generator` and
   `header.datamodel_versions`.
3. Writes only edges whose source and target are nodes of the same graph;
   relations across graphs are links.
4. Omits empty values rather than writing `null`.
5. Keeps, when it rewrites a file, the header keys it does not own (a title,
   a visibility set by another tool), the nodes' data and the edges'
   attributes, known or not.
6. Writes keys in a stable order, so that the same content gives the same bytes.
7. Never writes keys beginning with `x-` (see §6).

A writer MAY drop, when it rewrites a file, keys it does not know outside the
header and outside the nodes' data. An extension that must survive a round
trip through the official tools is a candidate for this specification.

## 5. Versions

Two numbers, two questions.

- **`header.version` — the form.** Semantic versioning: a new **major** means
  that a reader of the previous major cannot read the file, and is avoided; a new
  **minor** adds to the form without breaking any reader. `1.0` is the flat form
  and the container as written before this specification (August–October 2026);
  `1.1` is the container as specified here. Readers of 1.0 already read 1.1.
- **`header.schema_version` — the content.** An integer that grows when the
  content within the form changes in a way a migration may key off (absent = 0).
  History: 1 — edges may carry `attributes`; 2 — the canonical-document flags are
  spelled `is_canonical` / `em_canonical_document`.

The datamodel versions (`header.datamodel_versions`) are a third, independent
axis: they say which vocabulary the content uses.

## 6. Extensions

Anyone may add keys for their own needs. They must begin with **`x-`**
(`x-myproject-notes`), so that they never collide with a future key of this
specification. Readers ignore them (§3.1). The official tools (s3Dgraphy,
EMStudio, EM Tools, Heriverse, the StratiGraph server) never write them.

## 7. Conformance

- A **document** conforms when it validates against the schema of its version
  (`em.v1.1.schema.json` for the container; `em.v1.schema.json` for the flat 1.0
  form) and its edges join nodes of their own graph.
- A **reader** conforms when it reads every file of the conformance suite
  (`conformance/` beside this document) and obtains the expected result. It may
  add, for each graph, the default geo-position node its datamodel creates, and
  nothing else.
- A **writer** conforms when what it writes validates, and when reading and
  writing back each file of the suite loses nothing the specification describes.

The suite holds: a minimal file with one graph; a multigraph with shelf and
links; a georeferenced graph; a project with periodizations and horizons; a
legacy 1.0 flat file; a file with keys nobody knows.

## 8. Identifiers

The specification and its schemas are identified by persistent IRIs under
`https://w3id.org/extendedmatrix/`, which resolve to the Extended Matrix site.
In files and in prose the short prefix **`em:`** stands for the namespace of the
EM terms, `https://w3id.org/em/ontology#`: `em:hasSubEpoch` is
`https://w3id.org/em/ontology#hasSubEpoch`. The EM datamodel — nodes,
connections, qualia — is the formal language of Extended Matrix. Its terms map
to CIDOC CRM and its extensions, among them CRMem, the extension that declares
the concepts of argued reconstruction absent from the CIDOC family. Short in the files, long and
canonical in the world.

## 9. Examples

The smallest document — one graph, two units, one relation:

```json
{
  "header": {
    "format": "em.json",
    "version": "1.1",
    "schema_version": 2,
    "generator": {"tool": "s3dgraphy", "version": "1.6.0"},
    "datamodel_versions": {"nodes": "1.6.37", "connections": "1.6.48"}
  },
  "graphs": {
    "GT16": {
      "graph_id": "GT16",
      "nodes": [
        {"id": "us1", "node_type": "US", "name": "US1", "description": "Floor"},
        {"id": "us2", "node_type": "US", "name": "US2", "description": "Wall"}
      ],
      "edges": [
        {"id": "e1", "edge_type": "abuts", "source": "us1", "target": "us2"}
      ]
    }
  },
  "active_graph_id": "GT16"
}
```

The same relation with the contemporaneity it implies, derived by a tool:

```json
{"id": "us1_has_same_time_us2", "edge_type": "has_same_time",
 "source": "us1", "target": "us2",
 "attributes": {"origin": "derived", "derived_from": ["e1"]}}
```

A special member — the periodizations, with one horizon:

```json
"periodizations": {
  "graph_id": "periodizations",
  "data": {"em_collection": "Periodizations", "active_periodization": "per1"},
  "nodes": [
    {"id": "per1", "node_type": "periodization", "name": "Centuries"},
    {"id": "h1", "node_type": "horizon", "name": "2nd century AD",
     "data": {"start_time": 100, "end_time": 200, "color": "#c0504d", "order": 1}}
  ],
  "edges": [
    {"id": "h1_in_per1", "edge_type": "is_in_periodization", "source": "h1", "target": "per1"}
  ]
}
```

Complete files are in `conformance/`.

## 10. How to propose a change

Open an issue on the s3Dgraphy repository with the label `em-json`, or write to
the editor. Say what you need to carry and show a file. The editor decides;
an accepted change enters the Editor's Draft, is listed below, and is
published with the next release. A change that a reader of the current major
could not read is not accepted without a new major, and a new major is the
last resort.

## 11. Changes

- **1.2 — Editor's Draft, 30 October 2026.** Additive. §2.5 describes the site
  (a location of level `sito`, `virtual` for a supposed site), its footprint (a
  property whose value is a GeoSPARQL WKT with the CRS inside, `POLYGON` /
  `MULTIPOLYGON`, 2D or Z, at most 500 vertices inline) and the GIS layer as a
  resource (`gis_layer`, `gis_format`, `crs`, `bbox`, `feature_key`,
  `z_field`, a shapefile as a `file_set`), with the frame of a file and the
  rule «same grid, different code». No key of the container changes; the 1.1
  schema validates the files. Added on 28 October 2026 (decided by E.D.): §2.2,
  a property's value is written in `description` and mirrored in `data.value`;
  §2.4, a property is documented through its extractor, never straight to a
  document (connections datamodel 1.6.51, `read_only_sources`).
- **1.1 — 25 October 2026 (Release; Editor's Draft from 24 October).** First written specification. The
  container (in use since 13 August 2026) becomes the form of the file; the flat
  form of 1.0 stays readable. Optional blocks described: per-graph layout,
  shelf, DTC corpus, periodizations and horizons, links between graphs, the
  version of the work, landscape composition. Rule «readers ignore unknown keys»
  and the `x-` prefix for extensions. Policy of the two version numbers.
  Added on 25 October 2026, optional and additive: `header.profiles`, the
  community profiles a file uses (§2.7). At release: §1 distinguishes the
  language, the property graph, the container and the library; §2.2 and §8 place
  CRMem among the targets of the mapping.
- **1.0 — 11 July 2026.** Schema of the flat form (`header` + `graph` +
  `layout`), frozen with EMStudio's first save format.

## 12. How to cite

This is a draft: cite the release, version 1.1 —
Demetrescu, E. (ed.) (2026). *em.json — the Extended Matrix document format*,
version 1.1. CNR-ISPC. https://doi.org/10.5281/zenodo.23642465
