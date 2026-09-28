# HDT-O coverage in s3Dgraphy (P1-C)

Audit of HDT-O (ECHOES **D7.1**, May 2024) classes **HC1–HC20** and properties
**HP1–HP26+** against existing EM node/edge types. Scope of P1-C: *additive* —
add **only** the genuinely-missing, non-mappable classes as new node types (the
way `HDTNode → HC2` was seeded), gated out of the stratigrapher palette.

Namespaces already declared in `JSON_config/hdto_extension.ttl` (subset aligned
with D7.1); the RDF exporter emits a node's HDT-O type from its
`em_extension.uri` / `mapping.cidoc`.

Status legend: **mapped** = an existing EM node type already carries the class ·
**mappable** = an existing EM node covers it (annotate later, no new node) ·
**added** = new node type created in this session · **ontology-only** = RDF
superclass/infrastructure, no authoring node · **defer** = out of the core
authoring chain, add when a use-case needs it · **out-of-scope** = not an EM /
archaeology authoring concern.

## Classes (HC1–HC20)

| HC | Label | EM coverage | Status |
|----|-------|-------------|--------|
| HC1 | Heritage Entity | **`HeritageEntityNode`** (`hdto_nodes`, → `hdto:HC1` ⊂ `crm:E1`) | **added** |
| HC2 | Heritage Digital Twin | `HDTNode` (→ `hdto:HC2`) | mapped |
| HC3 | Tangible Heritage Entity | specialization of HC1 | defer |
| HC4 | Intangible Heritage Entity | specialization of HC1 | defer |
| HC5 | Digital Representation | `RepresentationModelNode` family — **Type-A annotated** `hdto:HC5` (keeps `crmdig:D1`) | **annotated** |
| HC6 | (unlabelled in D7.1 Draft-7) | — | ⚠ see note below |
| HC8 | 3D Model | `RepresentationModelNode` family, 3D side — declared in D7.1 with `HP21 is 3D representation output of` and `crmdig:D2/L20` | **to map** |
| HC7 | Digital Audiovisual Object | `RepresentationModel*` covers 3D; AV n/a | defer |
| HC9 | Study | **`StudyNode`** (`hdto_nodes`, → `hdto:HC9` ⊂ `crm:E7`) | **added** |
| HC10 | Heritage Valuation | — | defer |
| HC11 | Digital Twin Maintenance | — | defer (HDT lifecycle) |
| HC12 | Heritage Declaration Event | — | defer |
| HC13 | Project | **`ProjectNode`** (`hdto_nodes`, → `hdto:HC13` ⊂ `crm:E7`) | **added** |
| HC14 | Volatile Digital Object | superclass of HC2 (declared in `hdto_extension.ttl`; `HDTNode` `subclass_of` HC14) | ontology-only |
| HC15 | Persistent Digital Object | snapshot infrastructure (ttl) | defer / ontology-only |
| HC16 | Heritage Proposition Set | `GraphNode` = `em:EMGraph` (em.ttl declares `EMGraph ⊂ HC16`) | mapped |
| HC17 | Observation with Inference | `ParadataNode` — **Type-A annotated** `hdto:HC17` (keeps `crminf:I1`); Extractor/Combiner (I7/I5) remain the interpretation side | **annotated** |
| HC18 | Provenance Statement | GENESIS-side summary that links into the **DTC chain** (CRMdig + PROV-O); an HC18 links to ≥1 DTC chain. **NOT** Extractor/Combiner (those are CRMinf interpretation / HC17). | defer → DTC profile |
| HC19 | Provenance Assessment | GENESIS-side, paired with HC18 (CRMdig + PROV-O) | defer → DTC profile |
| HC20 | Criminal Activity | — | out-of-scope |

> HC21–HC29 (SensorThings API module) are a separate D7.1 section, out of P1-C scope.

> ⚠ **Corrected 28 September 2026, measured on `D7.1 - Draft-7-revVQ.docx`.** Two rows of this
> table were wrong and one was missing. **HC8 3D Model is declared in D7.1** — it has its own
> section, a scope note, the property `HP21 is 3D representation output of` towards HC1 and an
> alignment to `crmdig:D2 Digitization Process` / `crmdig:L20 has created` — and this table had no
> row for it at all; it is the class the case-study alignments in StratiGraph D3.1 use for 3D
> models, so the omission was ours. **HC6 has no section and no declared label** in that draft: it
> appears once, parenthetically, attached to «a resource page», so neither «Sensor» (what this
> table said) nor «Digital Document» nor «Sensor Data» can be confirmed, and HC6 should not be
> cited until D7.1 settles it. **HC3 is «Tangible Heritage Entity»** in D7.1, not the gloss
> «Tangible Aspect of an HC1» used here. HC9 Study likewise has a section although it is missing
> from the draft's own class list.


## Properties (HP1–HP26+) — mostly EDGES, not node types

The HDT granularity connectors already exist in
`s3Dgraphy_connections_datamodel.json` (no edge added this session — the HC1
chain works with them):

| HP | Label | EM edge | Status |
|----|-------|---------|--------|
| HP1 / HP1i | has digital twin / is digital twin of | `has_digital_twin` (Node → HDTNode) | present |
| HP3 / HP3i | (is/has) digital twin component of | `has_digital_twin_component` (HDTNode → HDTNode) | present |
| HP29 | has digital object part | `has_digital_object_part` (HDTNode → Representation*/Link) | present |
| HP33 / HP33i | contains / is proposition set of | `contains_proposition_set` (HDTNode → GraphNode) | present |
| HP23 | was about | `study_about_heritage` (StudyNode → HeritageEntityNode) | **added** |
| HP25 | has created | `study_produced_proposition_set` (StudyNode → GraphNode; range widened E31→HC16/E73) | **added** |
| (crm:P9) | consists of | `includes_study` (ProjectNode → StudyNode) — CRM fallback; D7.1 has no HC13→HC9 property | **added** |
| (crm:P46i) | forms part of | `heritage_part_of` (HeritageEntityNode → HeritageEntityNode) — CRM fallback; D7.1 has no HC1→HC1 property; E18 → tangible heritage | **added** |
| HP9 / HP21 / HP22 | is visual repr. / is 3D repr. output of / represents | EM representation edges | mappable |
| HP2, HP4–HP8, HP10, HP12–HP20, HP24, HP26 | story / narration / manifestation / valuation / disciplinary focus | — | defer (domains/ranges are deferred classes) |
| HP28, HP30–HP32, HP34 | snapshot / added-deleted-replaced content | — | defer (HC11 maintenance / versioning; ttl-only) |

## What was added (and why so little)

- **P1-C**: **HC1 `HeritageEntityNode`** — completes the core chain
  **HC1 → (HP1) → HC2 → (HP33) → HC16**.
- **HC9/HC13 session**: **HC9 `StudyNode`** and **HC13 `ProjectNode`** — the
  research-context framing agreed with E.D.: a graph = a **Study** whose content
  is a proposition set (HC16 = EMGraph), **about** an HC1, optionally under a
  **Project**:
  `Project ─includes(crm:P9)→ Study ─was_about(HP23)→ HeritageEntity`,
  `Study ─produced(HP25)→ GraphNode(HC16)`.
  Project→Study uses `crm:P9_consists_of` because D7.1 declares no direct
  HC13→HC9 property (documented in the edge + `hdto_extension.ttl`).
- **HC1-part / Type-A session**:
  - **HC1 part-whole** edge `heritage_part_of` (HeritageEntityNode →
    HeritageEntityNode) — e.g. the porphyry Tetrarchs forms part of San Marco.
    D7.1 has no HC1→HC1 property → `crm:P46i_forms_part_of` (E18, tangible),
    documented.
  - **Type-A annotations** (no new classes): `RepresentationModelNode` family
    also `hdto:HC5` (keeps `crmdig:D1`); `ParadataNode` also `hdto:HC17` (keeps
    `crminf:I1`) — added to each node's `em_extension.subclass_of`, so the
    exporter multi-types the instance.

Everything else HC1–HC20 stays mapped (HC2, HC16, HC14) or outside the
archaeology authoring scope — added the same
additive way when a concrete use-case needs it. In particular **HC18/HC19
(provenance)** are the GENESIS-side summary that links into the **DTC chain**
(CRMdig + PROV-O), distinct from the CRMinf interpretation side (HC17 /
Extractor / Combiner); their fine granularity is deferred to the **DTC profile**.

**Gating (HDT-O view):** HDT-O node types live in the datamodel and project to
RDF, but are **not** in the EMStudio palette allowlist (`palette-ui.ts`
`SECTIONS`), so the stratigrapher palette is unchanged. The dedicated
`hdto_nodes` datamodel section (HeritageEntityNode, StudyNode, ProjectNode) is
the machine-readable HDT-O-view grouping; `HDTNode`/`GraphNode` remain in
`container_nodes` (pre-existing HDT-O members).

**Verification:** `tests/test_hdto_projection.py` authors both an HC1→HC2→HC16
graph and a full Project→Study→HC1→HC2→HC16 graph and asserts the exporter emits
the HDT-O classes/properties (HC1/HC2/HC9/HC13, HP1/HP23/HP25/HP33, crm:P9) into
valid Turtle.
