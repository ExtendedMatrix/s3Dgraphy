.. _crmem:

CRMem — the Extended Matrix extension
=====================================

CRMem is the companion ontology of the Extended Matrix: the terms s3dgraphy
coins because the CIDOC CRM family has no way to say what the Extended Matrix
asserts. Its prefix is ``em:`` and its file is ``em.ttl``, shipped inside the
package at ``s3dgraphy/JSON_config/em.ttl``.

This page states what CRMem contains, what it deliberately does not contain, and
where its boundary with CRMinf runs. It is written for a reader who knows CIDOC
CRM and does not know the Extended Matrix.

Every class and property is listed, with its URI, its place in the hierarchy,
its scope note and a graph of its neighbourhood, in the `CRMem declarations
page <ontology/index.html>`_, regenerated from ``em.ttl`` at every build of this
documentation together with the Turtle (`em.ttl <ontology/em.ttl>`_) and RDF/XML
(`em.rdf <ontology/em.rdf>`_) serialisations.

.. contents::
   :local:
   :depth: 2


The criterion of extension
--------------------------

A class or a property enters CRMem only when it is needed to say **what the
Extended Matrix asserts about the non-observed, and on what basis**.

The virtual stratigraphic units — structural, non-structural, documentary — and
the virtual special find exist because no ontology in the family has a class for
*the entity that is not there and is argued to have been there*. A systematic
search of the official declarations of CIDOC CRM 7.1.3, CRMarchaeo 2.1.1,
CRMinf 1.2.1, CRMsci 3.2, CRMdig 5.0 and CRMgeo returns no term on "virtual",
"reconstruct" or "restoration"; the nearest, CRMsci's
``S8_Categorical_Hypothesis_Building``, names the *act* of forming a hypothesis,
not the hypothesised entity.

Two things follow from the same criterion, and both keep terms **out**.

*Descriptive scales are vocabularies, not extensions.* Taphonomic alteration
stages, masonry texture classes, functional typologies: CIDOC provides for these
explicitly, the scope note of ``E55_Type`` describing the class as "an interface
to domain specific ontologies and thesauri" and ``P2_has_type`` as the mechanism
of terminological specialisation. A term is coined in a SKOS module and attached
with ``P2_has_type``, without touching the ontology.

*A usage profile is not an extension.* The Data Transformation Chain projects
entirely onto CRMdig with a parallel PROV-O projection and introduces not one
term of its own. See :doc:`dtc-profile`.


The classes
-----------

CRMem declares **45 classes and 41 properties** (26 object, 15 datatype),
measured by parsing ``em.ttl``. The classes are the constructs of the Extended
Matrix itself — what a stratigraphic record made in this language *contains* —
and they are the larger half of the extension. The properties, four of them, are
the relations between those constructs that the family cannot express.

One rule governs the whole class inventory, and it is what to check it against:

.. admonition:: The rule

   **Every class declared in CRMem is a subclass of at least one class of the
   reference family. None stands free.** What the extension adds is never a new
   top-level kind of thing, but a distinction the family does not draw at the
   granularity the discipline needs. The superclass is what keeps the addition
   legible to a consumer that reads CIDOC and has never heard of the Extended
   Matrix.

The virtual family
~~~~~~~~~~~~~~~~~~

This is the semantic heart of the model and the clearest case of the rule:

.. code-block:: turtle

   em:VirtualSU
       a owl:Class ;
       rdfs:subClassOf crminf:I4_Proposition_Set , crmarchaeo:A8_Stratigraphic_Unit .

Two parents at once, and that is the whole point. A hypothesised unit **is** a
proposition set — it is argued, and its argumentation chain is in the graph —
and it **is** a stratigraphic unit, taking its place in the sequence exactly as
an observed one does. That double parentage is the two-tier structure of the
Extended Matrix written as one axiom. ``crmarchaeo:A2_Stratigraphic_Volume_Unit``
would have been wrong: A2 is a physical volume, and a virtual unit has none.

Beneath it sit the three kinds the method distinguishes — ``em:StructuralVirtualSU``
(USVs), ``em:NonStructuralVirtualSU`` (USVn), ``em:DocumentaryVirtualSU`` (USD) —
which differ by *what sustains them*, not by their standing in the sequence.
``em:VirtualSpecialFind`` repeats the pattern one level down, at once
``crm:E89_Propositional_Object`` and ``crm:E19_Physical_Object``, and names the
argued reassembly of a fragmented artefact.

The units that are not volumes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``em:NegativeSU`` (USN) and ``em:NeutralSU`` (USNt) are declared beneath
``crmarchaeo:A3_Stratigraphic_Interface``, not beneath the unit. What they record
is an **absence that is nevertheless a stratigraphic fact** — a cut, a void, a
surface of separation — and modelling them as thin volumes is the error that
makes a sequence unreasonable.

Beside them, ``em:DisplacedSpecialFind`` and ``em:ReusedSpecialFind`` are
physical objects, the second also ``crmarchaeo:A2``, which is what lets a
*spolium* be at once an object with a history of its own and a unit in the
sequence that received it.

The division mirrors CRMarchaeo's own rather than departing from it. Verified
against the 2.1.1 declarations: ``A2_Stratigraphic_Volume_Unit`` and
``A3_Stratigraphic_Interface`` are **both declared subclasses of**
``A8_Stratigraphic_Unit``, which is itself a subclass of
``crmsci:S20_Rigid_Physical_Feature``. So the abstract EM stratigraphic node
sits on A8, an observed unit on A2, a negative or neutral one on A3 — three
levels of the operational model against three levels of the reference
ontology, agreeing without being forced to.

.. note::

   **One cell of that table is empty, in CRMarchaeo as well as here.** A2 is the
   positive volume and A3 the interface; a **negative volume** — a void that has
   extent, an emptied pit, a cavity — is neither, and the archaeological
   extension declares no third sibling under A8 for it. The Extended Matrix does
   not model it either. It is named here because a gap that can be stated is
   scheduled work, and because this one is a candidate either for CRMem under the
   criterion above or for a proposal to the CRMarchaeo SIG — which of the two is
   an open question, not an oversight.

The rest, briefly
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 34 40 26

   * - CRMem class
     - Declared beneath
     - What it records
   * - ``em:StratigraphicEvent``, ``em:TransformationSU``
     - ``crmarchaeo:A5_Stratigraphic_Modification``
     - a change, not a thing
   * - ``em:WorkingUnit``
     - ``crm:E25_Human-Made_Feature``
     - an operational unit of the excavation
   * - ``em:ContinuityNode``
     - ``crm:E64_End_of_Existence``
     - how the model says something stops
   * - ``em:Paradata``, ``em:Extractor``, ``em:Combiner``
     - ``crminf:I1_Argumentation``, ``I7_Belief_Adoption``, ``I5_Inference_Making``
     - the argumentation triad, adding nothing to CRMinf
   * - ``em:TimeBranch``
     - ``crm:E4_Period``
     - an alternative temporal scenario
   * - ``em:RepresentationModel`` (+3 subclasses)
     - ``crmdig:D1_Digital_Object``
     - what stands for a unit in three dimensions
   * - ``em:SemanticShape``, ``em:AnnotationRegion``
     - ``crm:E73_Information_Object``, ``crm:E36_Visual_Item``
     - schematic stand-in; region of an image
   * - ``em:FunctionalUnit``
     - ``crm:E24_Physical_Human-Made_Thing``
     - a cut and its fill, a wall and its foundation

The paradata triad is why **CRMinf is a formal dependency of CRMem** and not
merely a neighbour: three CRMem classes are declared directly beneath three
CRMinf classes and add nothing to them.

Forty-two of the forty-five classes are cited by the node datamodel shipped with
the library, in the ``em_extension`` block of the node type that instantiates
them; the remaining three (``em:Author``, ``em:VirtualSU``,
``em:RepresentationModel``) are abstract parents that no concrete type
instantiates. The intent is that the ontology and the operational type system be
**one declaration**, and the two are currently consistent on every class name.

.. warning::

   They are **not** yet consistent on every axiom, and nothing checks them.
   ``em.ttl`` is hand-authored and sits outside the generation chain that guards
   the rest: five ``em_extension.subclass_of`` declarations in the node datamodel
   assert a parent the ontology does not carry — ``em:AIAuthor`` also
   ``crm:E39_Actor``; ``em:Paradata`` also ``hdto:HC17_Observation_with_Inference``;
   and the three representation models also ``hdto:HC5_Digital_Representation``.
   Whether those parents belong in the ontology is a modelling decision, not a
   transcription error. A check that compares the two is a small tool and does
   not exist.


The properties
--------------

CRMem declares four properties, and **none of them introduces a class of its
own**: each hangs on classes that already exist, whether CIDOC core or, for the
time branch, one the language declares for its own constructs (above). Each is
listed with the ceiling it hangs under, where an honest one exists, and the gap
it names.

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - Term
     - Ceiling
     - The gap it names
   * - ``em:isInActivity``
     - **none, deliberately**
     - Classification of an arbitrary entity under an activity-shaped grouping.
       See below.
   * - ``em:contrastsWith``
     - none available
     - Mutual exclusivity between two alternative reconstructions of the same
       interval. ``P15_was_influenced_by`` has ``E7 Activity`` as its domain and
       a time branch is an ``E4 Period``, so there is no honest superproperty.
   * - ``em:belongsToAlternative``
     - ``rdfs:subPropertyOf crminf:J28i_is_referred_to_in``
     - Membership of an entity in an alternative scenario. CRMinf does cover
       this, so the extension *narrows* here rather than widening: the term
       exists to name the EM-specific reading, under a CRMinf ceiling.
   * - ``em:hasSemanticShape``
     - none available
     - The proximity geometry of a unit — *where it is held to be*, not how it
       looks. ``P156`` / ``P161`` do not reach, because since the
       proxy-as-property change the source of this relation includes a
       ``PropertyNode``, and a quale does not occupy a place.

.. note::

   **Implementation state, measured on the working tree, 24 September 2026.**
   All four properties are declared in ``em.ttl`` (v1.6.4) and wired in the
   connections datamodel (v1.6.18): ``em:isInActivity``, ``em:contrastsWith``,
   ``em:belongsToAlternative`` and ``em:hasSemanticShape``. The unregistered
   ``CIDOC-S3D:`` prefix is **gone from every live field** of both datamodels —
   three of its names became the corresponding ``em:`` property, and three were
   removed outright because ``crm:P106i_forms_part_of``,
   ``crm:P129i_is_subject_of`` and ``crm:P138i_has_representation`` already say
   what was meant once the target is typed correctly. It survives only in the
   historical notes of the datamodel descriptions, which is the record of what
   changed. Bumping the two datamodels made the eight shipped mapping
   descriptors report a stale ``_validated_against`` stamp on the next check,
   unprompted; they were re-stamped. See :doc:`mapping-update-procedure`.


Relations that resolve inside CIDOC
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Three relations of the Extended Matrix read, from inside the model, as though
they needed a predicate of their own. They do not: each resolves against an
existing CIDOC property once the target is typed correctly. They are recorded
here because the question recurs, and because the remedy is in each case a
modelling decision a reader may want to check.

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - Relation
     - What CIDOC provides
     - Why no new term is needed
   * - 3D representation of a unit
     - ``crm:P138i_has_representation``
     - **A matter of co-typing, not of predicate.** “3D” belongs in the
       ``rdf:type`` of the target, not in the relation. Co-typing the model as
       ``E36_Visual_Item`` says it — ``D1`` and ``E36`` are both under ``E73``
       and are not disjoint — and the same pattern already serves
       ``has_visual_reference``.
   * - Membership in a paradata group
     - ``crm:P106i_forms_part_of``
     - **A matter of class and of direction.** The group must not be typed
       ``E78 Collection`` — a class CIDOC 7.1 renamed, and whose successor
       ``E78_Curated_Holding`` is a subclass of ``E24 Physical Human-Made
       Thing``, which a set of nodes is not. Typed correctly the membership
       predicate already exists, and emitted through the inverse it reads the
       right way round.
   * - Documentation attached to a unit
     - ``crm:P129i_is_subject_of``
     - **A distinction carried by the target’s type.** “The paradata
       container” versus “everything that mentions this unit” is a
       difference in the *type of the target*, not a difference of predicate.


``em:isInActivity`` in full
---------------------------

This is the first CRMem term to be implemented, and it carries the argument for
the others, so it is given in full.

.. code-block:: turtle

   em:isInActivity
       a owl:ObjectProperty ;
       rdfs:label "is in activity"@en ;
       rdfs:domain crm:E1_CRM_Entity ;
       rdfs:range  crm:E7_Activity .

**No class is introduced for this property.** ``crm:E7_Activity`` is CIDOC core
— a subclass of ``E5_Event``, declared in CRM 7.1.3 — and the EM activity group
stays mapped to it. Only the property is ours. (CRMem does declare classes, for
the constructs of the language itself: see `The classes`_ above.)

The scope note
~~~~~~~~~~~~~~

CIDOC can say that an actor **participated in** an event (``P11i``), that a thing
**was present at** one (``P12i``), that an object **was used for** one
(``P16i``). It cannot say that an arbitrary entity — a stratigraphic unit, a
quale, a document, an extractor, a whole paradata group — is **classified under**
an activity-shaped grouping.

That is the axis of **intention** in the Extended Matrix, orthogonal to space
(``is_in_location``) and to time (the epoch relations), and it is a curatorial
grouping rather than an event anyone attended.

Why there is no superproperty
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each candidate was checked and each fails for a stateable reason:

* ``P11i_participated_in`` requires an ``E39 Actor`` in the subject; the sources
  here are not actors.
* ``P12i_was_present_at`` would pass the type check — ``E28 Conceptual Object``
  reaches ``E77`` through ``E71``/``E70`` — but it would be **false**. A property
  node attended nothing.
* ``P9i_forms_part_of`` requires an ``E4 Period`` in the subject; none of the
  sources is a period.
* ``P129i_is_subject_of`` requires an ``E89 Propositional Object`` in the object;
  ``E7 Activity`` has ancestors ``E5``/``E4``/``E2``/``E1``/``E92`` and is not
  one.
* CRMarchaeo 2.1.1 offers no alternative: it has specific archaeological
  activities (``A9_Archaeological_Excavation``, ``A1_Excavation_Processing_Unit``,
  ``A6_Group_Declaration_Event``) but **no generic activity class**, and none of
  its 32 ``AP`` properties expresses membership in one. Verified against the
  full parsed release.

Declaring the absence of a superproperty is itself a claim, and it is made
explicitly rather than by omission.

Why the name
~~~~~~~~~~~~

The term replaces a dead desideratum called ``participatedInActivity``. It is
**not** called that, because participation is a claim this model does not make,
and the imprecision is the kind a reviewer notices at first sight.

How it is emitted
~~~~~~~~~~~~~~~~~

The edge's ``mapping.cidoc`` is left **empty on purpose** — a declaration that no
CIDOC predicate holds, not a gap — and the serializer was changed so that a
*declared-absent* edge is emitted on its extension predicate alone rather than
staying silent. Silence was correct only while there was nothing true to say. A
CRM-only reader still sees nothing on this relation, which is correct, instead of
seeing something false.


The boundary with CRMinf
------------------------

CRMinf is asked two different questions and gives two different answers, and the
distinction is the first objection a reviewer will raise.

**CRMinf covers membership.** An entity's belonging to a set of propositions is
expressed by ``J28``/``J28i``, and since 1.2 by the ``I17`` pattern with
``J30``/``J31``/``J32``. So ``em:belongsToAlternative`` hangs beneath CRMinf and
the extension narrows there rather than widening.

**CRMinf does not cover incompatibility.** Its 52 ``J`` properties speak of
premises, conclusions, adoption, provenance and meaning; none states that two
beliefs exclude one another. This is not an oversight: CRMinf models *how one
arrives at* a belief, not the logical relations *between* beliefs. That sentence
belongs in the scope note of ``em:contrastsWith``, because it is the objection
that will arrive.

**CRMinf is a formal dependency of CRMem**, and since 24 September 2026 it is
exercised rather than merely asserted: three CRMem classes are declared directly
beneath ``I1_Argumentation``, ``I7_Belief_Adoption`` and ``I5_Inference_Making``,
``em:VirtualSU`` beneath ``I4_Proposition_Set``, and ``em:belongsToAlternative``
beneath ``J28i_is_referred_to_in``. The dependency lives in the ontology file;
no CRMinf IRI is emitted directly from the connections datamodel, which is a
different statement and remains true.
Typing ``em:TimeBranch`` also as ``crminf:I4_Proposition_Set`` is the open
modelling decision attached to it: what is incompatible are propositions, not
periods.


Graph, study and digital twin
-----------------------------

StratiGraph D3.1 §3.3 and D3.2 §3.5 say it in one sentence: *a graph is a
study: its content is a proposition set*. The sentence is read as a
correspondence, not as a shared class.

An Extended Matrix graph corresponds one to one to the study that produced it.
The study is ``hdto:HC9_Study`` (``StudyNode``): the investigation as an act. It
is about a heritage entity (``hdto:HP23_was_about``), it may form part of a
project (``hdto:HC13``, through ``crm:P9_consists_of``), and it created the graph
(``hdto:HP25_has_created``). The graph, ``em:EMGraph``, is what the study
asserts: an ``hdto:HC16_Heritage_Proposition_Set``, also a ``crm:E73`` and a
``prov:Bundle``.

``em:EMGraph`` is deliberately not a subclass of ``hdto:HC9``. HC9 descends from
``crm:E65_Creation`` and so from ``E2 Temporal Entity``; HC16 descends from
``crminf:I4_Proposition_Set`` and so from ``E77 Persistent Item``; CIDOC CRM
declares the two disjoint. Saying that a graph *is* a study is therefore the
practice of the method — one file, one study — expressed in the ontology as two
classes joined by HP25.

The graph is not the digital twin. An ``hdto:HC2_Heritage_Digital_Twin`` gathers
all the digital information about a heritage asset, at any scale: a whole
building, or one inscribed block that has a twin of its own. A twin can contain
the proposition sets of several studies (``hdto:HP33_contains``); one twin is
never one graph.


Namespace
---------

The prefix is ``em:``. CRMem follows the family's naming convention — CRMarchaeo,
CRMsci, CRMdig, CRMgeo, CRMinf — and replaces two earlier names that pointed at
nothing anyone could look up: ``CIDOC-S3D`` (a prefix written on nine edges and
never registered, removed from both datamodels on 24 September 2026) and
``CRMs3D`` (a metadata label).

.. warning::

   The canonical namespace is ``w3id.org/extendedmatrix``. ``w3id.org/em`` was
   **deliberately not registered**: two letters are too weak an identifier to
   carry a permanent namespace, and ``em`` collides with a dozen other uses.
   ``w3id.org/extendedmatrix/`` and ``/vocab/`` resolve today;
   ``/extendedmatrix/ontology`` does not yet serve content.

   ⚠ The shipped RDF still emits ``w3id.org/em/ontology#``. That is the real
   misalignment — not a missing registration, but code emitting an address the
   project decided against. Until it is changed, the IRIs in delivered RDF are
   stable as identifiers and are not the canonical ones.


A lesson worth carrying
-----------------------

One finding from the verification generalises beyond this ontology and is
recorded here because it cost real time.

**A URL containing a version number does not prove the version.** CRMgeo is the
only extension in the family without a stable release on the institutional
namespace: the only stable RDFS serialization lives on the FORTH-ICS namespace,
while what is served under a path containing the version number is a preparatory
draft that says of itself, in its own ``owl:versionInfo``, that it may be used
only as a draft — and that has removed roughly a dozen classes and properties
relative to the stable version. Read ``owl:versionInfo``, always.
