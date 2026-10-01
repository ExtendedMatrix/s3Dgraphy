(generated-report)=

# Generated figures

<!-- GENERATED, do not edit by hand. Regenerated on every documentation build; see docs/conf.py. -->

Every figure on this page is read off the datamodels and the installed package at build time. **No count in this documentation is written by hand**; where another page needs one, it links here.

## Declared coherence horizon

| Component | Version |
| --- | --- |
| s3dgraphy (library) | 1.6.0.dev27 |
| nodes datamodel | 1.6.22 |
| connections datamodel | 1.6.35 |
| qualia datamodel | 1.6.6 |
| CIDOC-CRM | 7.1.3 |
| CRMarchaeo | 2.1.1 |
| CRMsci | 3.2 |
| CRMdig | 5.0 |
| CRMgeo | 1.2 |
| CRMinf | 1.2.1 |
| HDT-O | 1.0 |
| PROV-O | W3C Recommendation 2013-04-30 |
| CRMem | 1.6.12 |

## Node types

The three populations, named apart — see this module's docstring for why there is no single number.

| What | Count |
| --- | --- |
| declared in the node datamodel | 57 |
| — of which authorable types | 53 |
| — of which abstract family bases | 4 |
| field-level mapping blocks (not node types) | 3 |
| entries with no mapping block | 0 |

Abstract family bases: `GroupNode`, `Node`, `ParadataNode`, `StratigraphicNode`.

## Edge types

| What | Count |
| --- | --- |
| declared in the connections datamodel | 59 |
| — of which live (not deprecated) | 58 |
| — declaring a named reverse direction | 52 |

## Python classes

| What | Count |
| --- | --- |
| Python node classes in the generated registry | 60 |
| — of which abstract (no own node_type) | 3 |
| present in the registry, absent from the datamodel | 3 |

Abstract classes (no own `node_type`): `DTCNode`, `RepresentationNode`, `VirtualStratigraphicUnit`.

Classes present in the registry with no entry in the node datamodel, and therefore with no declared CIDOC projection: `DTCNode`, `RepresentationNode`, `VirtualStratigraphicUnit`.

## Other surfaces

| What | Count |
| --- | --- |
| public API callables | 215 |
| test modules in tests/ | 144 |
| test modules in tests/*/ | 66 |

## Alignment by ontology

Of the 57 node types declared, **14 reuse a class from an existing ontology unchanged** and **43 declare a class in the Extended Matrix namespace**. Every one of the latter keeps a CIDOC anchor, so the table below covers all of them.

Node types, by the ontology of the CIDOC class they are anchored to:

| Ontology | Node types |
| --- | --- |
| crm | 30 |
| crmarchaeo | 13 |
| crmdig | 7 |
| hdto | 4 |
| crminf | 3 |

Edge types, by the ontology of the CIDOC predicate they emit. An edge with no CIDOC predicate is a *declared absence*: the family has no term for that relation and the edge is emitted on its extension predicate alone.

| Ontology | Edge types |
| --- | --- |
| crm | 33 |
| (none declared) | 10 |
| crmdig | 6 |
| hdto | 6 |
| crmarchaeo | 2 |
| prov | 2 |

Edge types carrying a second, extension predicate beside (or instead of) the CIDOC one:

| Ontology | Edge types |
| --- | --- |
| em | 14 |
| CRMarchaeo | 11 |
| prov | 6 |
| CIDOC-CRM | 5 |
| CRMdig | 2 |
| CRMinf | 2 |

Every extension prefix declared above resolves in the RDF exporter's prefix table.

