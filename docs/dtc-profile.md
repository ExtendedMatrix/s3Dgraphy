(dtc-profile)=
# The DTC profile — a usage profile of CRMdig

The **Data Transformation Chain (DTC)** profile records the digital provenance
that *produces documents*: what was acquired, what happened to it, and what came
out.

## Read this first

> **The DTC profile is a usage profile of CRMdig. It introduces zero classes and
> zero properties of its own. Its RDF projection is entirely CRMdig, with a
> parallel PROV-O projection, and its declared status is
> `profile-DTC-ECHOES`.**

This has to be stated at the top, and stated flatly, because it is the first
thing a reader assumes the other way round. The DTC has its own node classes in
the Python library, its own section in the node datamodel, its own palette and
its own glyph family — everything that *looks* like an ontology extension. It is
not one. Every term it emits is somebody else's, and that is a design result, not
an accident of implementation.

The measurement behind the claim: the DTC node types declare `em_extension.uri`
values that point straight at `crmdig:D7`, `crmdig:D12` and `crmdig:D8`; the four
chain edges map to `crmdig:L10`, `L11`, `L21` and `L12`; and no `em:` term is
declared or emitted anywhere in the profile.

Contrast with {doc}`crmem`, which *is* an extension and says why for each of its
four terms. The two documents are deliberately symmetrical: one names what had to
be coined, the other names what did not.

## Where the profile sits

The DTC is **distinct from EM paradata**. EM paradata — extractors, combiners,
property nodes, projected onto CRMinf — is *interpretation performed on a
document*. The DTC is *how the digital objects themselves came to be*. The two
meet at the document: a DTC output may later be the same digital object an EM
document node wraps.

Funding seam: the DTC profile is the identifiable **ECHOES** contribution; the
substrate it plugs into — s3dgraphy, the EM language, the projection machinery —
is StratiGraph / OSS. Keeping the profile as a gated section of the datamodel
keeps that contribution cleanly identifiable inside a shared library.

## The shape of a chain

The chain is made of **resources connected by events**. This is the part most
often mis-described, so it is worth being exact: inputs and outputs are **not**
dedicated classes. Both are the ordinary EM `ResourceNode` — the shared hinge to
an external file or URL that a representation model or a document may also
reference. A resource that takes part in a chain carries a `dtc_kind` and
projects as `crmdig:D1_Digital_Object` + `prov:Entity` + `P2_has_type`.

What *is* a dedicated class is the **event**, and there are two kinds of it,
distinguished by type and never conflated:

| Class | `node_type` | rdf:type | Role |
|---|---|---|---|
| `DTCProcessNode` | `dtc_process` | `crmdig:D7_Digital_Machine_Event` ⊂ `prov:Activity` | **Genesis**: the transformation that turns inputs into produced objects |
| `DTCAcquisitionNode` | `dtc_acquisition` | `crmdig:D12_Data_Transfer_Event` (⊂ D7) for a retrieval; a capture takes its kind's class: `crmdig:D2_Digitization_Process` (photo, laserscanner), `crmdig:D11_Digital_Measurement_Event` (topographic, gnss_survey), `crm:E65_Creation` (field_drawing, recording_sheet) — `dtc_kinds.acquisition.<kind>.mapping` | **Acquisition**: how an asset enters this study — made here (capture) or arriving from an opaque external source (retrieval) |
| `DTCDeviceNode` | `dtc_device` | `crmdig:D8_Digital_Device` | The apparatus a step happened *on* — context, not a step |

`DTCProcessNode` and `DTCAcquisitionNode` share an abstract base, `DTCNode`
(registry `node_type = None`), so tooling can group them by ancestry — the same
arrangement as the stratigraphic family. `DTCDeviceNode` sits outside that base
on purpose: it is not a step of the chain.

### The chain edges

| Edge | Direction | CRMdig | PROV-O |
|---|---|---|---|
| `dtc_had_input` | event → resource | `crmdig:L10_had_input` | `prov:used` |
| `dtc_had_output` | event → resource | `crmdig:L11_had_output` | `prov:generated` |
| `dtc_derived_from` | resource → resource | `crmdig:L21_used_as_derivation_source` | `prov:wasDerivedFrom` |
| `dtc_happened_on_device` | event → device | `crmdig:L12_happened_on_device` | *(none, deliberately)* |

`dtc_had_input` also accepts another event as its target, so a declared
derivation can name a whole acquisition as its input — one edge instead of five
hundred. That case projects as `prov:wasInformedBy` rather than `prov:used`,
which ranges over digital objects and would be wrong for an event.

`dtc_happened_on_device` has **no PROV-O projection on purpose**: `prov:used` is
already taken by `dtc_had_input`, and `prov:Agent` ranges over things that bear
responsibility, which a camera does not.

### Chain versus context

An edge carries a `dtc_role` when it is part of the chain a provenance walk may
traverse. An edge **without** one is context by construction, and a walk does not
enter it — which is why the device edge exists without making a device a step.
The datamodel says this once and both the library and its clients read it there;
it used to be written twice, once by node name and once by name prefix on the
client, and a `dtc_*` edge that was context would have been traversable on one
side and not the other.

## The per-kind vocabulary is data

The *specific* kind of a step or a resource (`data.dtc_kind`) comes from a
vocabulary in `em_visual_rules.json → dtc_kinds`, read through
`utils.get_dtc_kinds()` and validated in the node constructors. **Adding a kind
is a JSON entry plus a glyph, not a code change.**

The axes currently declared, measured on the shipped file:

- **acquisition** — two families (since em_visual_rules 1.6.22), stated per kind
  as `family`:
  - *capture* — `photo`, `laserscanner`, `topographic`, `gnss_survey`,
    `field_drawing`, `recording_sheet`: the object is MADE by the act;
  - *retrieval* — `download`, `local_import`, `uri_reference`, `ingest`: it
    arrives already made.
- **process** — `photogrammetry`, `transformation`, `decimation`,
  `georeferencing`, `format_conversion`, `export`, `lod_generation`, `tiling`,
  `packing`, `classification`, `vectorization` (the four gestures of whoever
  exports since visual rules 1.6.29, dev28)
- **output** — `pointcloud`, `mesh`, `dem`, `orthophoto`, `points`, `lines`, `polygons`
- **device** — `camera`, `sensor`, `drone`, `computer`, `scanner`, `total_station`, `gnss`
- **input** — no entries: a read alias of the capture family
  (`get_dtc_kinds()["input"]`), for readers that still ask it.

The acquisition, process and output axes say how material entered, what happened
and what came out; `device` says what it happened **on**.

`dtc_kind` projects as `crm:P2_has_type`.

```{note}
**The captures left `input` with their keys.** Until 1.6.21 `photo`,
`laserscanner` and `topographic` sat on an `input` axis that nothing validated
any more (DTCInputNode is retired). They are now captures of the acquisition
axis, under the SAME keys — a stamp or a node carries the kind, never the axis,
so nothing already written changes meaning. A stamp's definitive form is
`how.dtc_kind = "photo"`; EMStudio's provisional `local_import` +
`how.acquisition.capture` is still read (`s3dgraphy.dtc.capture`). The apparatus
stays apart: `laserscanner` is the capture, `device.scanner` the scanner.
```

## EM commons are reused, not duplicated

No agent, licence, embargo or file class was introduced for the DTC.

| Concern | Reused EM node and edge | Projection |
|---|---|---|
| Agent | `AuthorNode` via `has_author` (source includes `DTCNode`) | `prov:wasAttributedTo`, `em:hasAuthor` |
| File pointer | `ResourceNode` via `has_linked_resource` | `crm:P67_refers_to`, `crmdig:L19_stores` |
| Rights | `LicenseNode` via `has_license`; `EmbargoNode` via `has_embargo` | `crm:P104_is_subject_to` |

## Two conceptual distinctions worth carrying

**A proxy and a representation model have different epistemic status.** The proxy
is cumulative and argued — synthesised from several sources, photogrammetry plus
drawn survey — and states the extent of a unit *as it is held to be*. The
representation model is a **dated document**: good for one epoch, possibly
partial. The counter-intuitive consequence is that **the proxy is more complete
and the model is more detailed**, and therefore that the model's silence is not
informative (it does not distinguish "not modelled" from "not declared" from
"partly visible") while the proxy's silence is.

**A model's date has no field of its own, and should not have one.** It travels
through the resource layer: `has_linked_resource` → `ResourceNode` →
`dtc_had_output` → the DTC event that produced it. A second place to record it
would be a second thing to keep true.

## Verification

`tests/test_dtc_projection.py` authors a chain (photos → transformation → mesh,
with an author, a linked file, and an output derived from the photos) and asserts
that the projected Turtle carries the CRMdig classes and predicates, the PROV-O
ones, the `P2_has_type` kinds and the reused commons; plus data-driven kind
validation, an em.json round trip, and the palette-gating check. Further DTC
coverage is in `test_dtc_corpus.py`, `test_dtc_ingest.py`,
`test_dtc_neighbourhood.py` and `test_dtc_residency.py`.

## Deferred, recorded so that scope stays legible

- DTC glyphs and the visual manager (the SVG set is already named per kind in
  `dtc_kinds.*.glyph`).
- The DTC lens and its double-click seam.
- Shared-UUID identity between a DTC output and an EM document — both are digital
  objects, and this model does not preclude it.
- Provenance summary nodes on the HDT-O side linking into this chain.
- A rig — a sensor mounted on a drone — is an assembly of two devices and has no
  edge yet. The glyph family says it by drawing their connectors touching, which
  is a picture and not a statement.
