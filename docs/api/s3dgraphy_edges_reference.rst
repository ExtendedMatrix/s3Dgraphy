s3dgraphy Edges Reference
=============================

This document provides comprehensive documentation for all edge types in s3dgraphy, including their semantic meanings, CIDOC-CRM mappings, and usage patterns.

Overview
--------

Edges in s3dgraphy represent relationships between nodes in the archaeological knowledge graph. Each edge type has specific semantic meaning and follows archaeological documentation standards.

.. note::

   **Datamodel version**: connections datamodel **v1.5.5** ships **37
   canonical edge types** and **30 distinct reverse names** (67 names
   total). All canonical types are listed below, grouped by domain. The
   reverse-edge pattern is documented in the next section before the
   classification.

.. _canonical-reverse-edges:

Canonical / Reverse / Symmetric Pattern
---------------------------------------

Since datamodel v1.5.3 every edge in s3dgraphy is *one of three kinds*:

**Canonical edges**
   Have a single semantic direction. The canonical name is the one
   registered in :data:`s3dgraphy.edges.edge.EDGE_TYPES`; the reverse is
   computed on demand from the JSON datamodel via
   :meth:`Edge.get_reverse_name`. Canonical example: ``is_after``,
   ``cuts``, ``has_property``.

**Reverse edges**
   The named inverse of a canonical edge. They live in the JSON
   datamodel under the ``reverse: { name, label }`` block of their
   canonical sibling, never as a standalone entry. Reverse example:
   ``is_before`` is the reverse of ``is_after``; ``is_cut_by`` is the
   reverse of ``cuts``. Edges constructed with the *canonical* name and
   queried via :meth:`Edge.is_canonical` return ``True``; calling
   :meth:`Edge.get_reverse_name` returns the reverse string.

**Symmetric edges**
   Have ``reverse = None`` in the datamodel — direction is meaningless.
   The current symmetric set is ``bonded_to``, ``equals``,
   ``is_bonded_to``, ``is_physically_equal_to``, ``has_same_time``. For
   these edges :meth:`Edge.is_symmetric` returns ``True`` and the
   exporter emits a single arc with no implicit reverse.

The schema enforces the canonical direction at *write* time
(:meth:`Graph.add_edge` raises ``ValueError`` on an unknown edge type)
but accepts either direction at *read* time — :meth:`Edge.get_reverse_name`
lets node editors (e.g. yEd, em-graph) label sockets with the right verb
without re-implementing the lookup. See :doc:`/s3dgraphy_core_concepts`
for the conceptual motivation; the per-edge tables below note the
reverse name in the ``Reverse`` field.

Edge Types Classification
--------------------------

Temporal Relationships
~~~~~~~~~~~~~~~~~~~~~~

**is_after**
^^^^^^^^^^^^

:Label: Is after
:Description: Indicates a temporal sequence where one item occurs after another. This is the **canonical** direction in Extended Matrix (from more recent to more ancient stratigraphic units).
:CIDOC-CRM: P120_occurs_before
:CRMarchaeo: AP28_occurs_before
:Reverse: ``is_before`` ("Is before")
:Visual Style: Solid line
:Usage: Primary stratigraphic relationships

.. code-block:: python

   # Canonical: recent -> ancient
   # US002 (wall) sits on US001 (foundation): the wall is more recent
   graph.add_edge("rel001", "US002", "US001", "is_after")

**Allowed Connections:**
   - StratigraphicNode → StratigraphicNode

**is_before** *(reverse of* ``is_after`` *)*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Is before
:Description: Reverse name of ``is_after``. Use the canonical ``is_after``
   when *writing* an edge; ``is_before`` is what
   :meth:`Edge.get_reverse_name` returns for the reverse-direction label.

.. note::

   Pre-1.5.3 code that constructed ``is_before`` edges directly will fail
   :meth:`Graph.add_edge` validation. Migrate to ``is_after`` and let the
   consumer call :meth:`Edge.get_reverse_name` for UI labels.

**has_same_time**
^^^^^^^^^^^^^^^^^

:Label: Contemporaneous Elements
:Description: Indicates that two elements are contemporaneous
:CIDOC-CRM: P114_is_equal_in_time_to
:Visual Style: Double line
:Usage: Contemporary archaeological features

.. code-block:: python

   # Contemporary features: wall and floor built at same time
   graph.add_edge("rel002", "US001_wall", "US002_floor", "has_same_time")

**Allowed Connections:**
   - StratigraphicNode → StratigraphicNode
   - SpecialFindUnit → SpecialFindUnit

**changed_from**
^^^^^^^^^^^^^^^^

:Label: Temporal Transformation
:Description: Represents an object that changes over time
:CIDOC-CRM: P123_resulted_from
:Reverse: ``changed_to`` ("Changed to")
:Visual Style: Dotted line
:Usage: Transformation processes, reconstruction phases

.. code-block:: python

   # Building transformation: medieval wall reuses Roman foundation
   graph.add_edge("trans001", "US005_medieval_wall", "US010_roman_foundation", "changed_from")

**Allowed Connections:**
   - StratigraphicNode → StratigraphicNode (any subtype, including container nodes)
   - TransformationStratigraphicUnit → StratigraphicNode

.. note::
   When multiple nodes are linked by ``changed_from`` edges, they form an **instance chain** --
   a connected component representing the complete biography of a single physical object
   through time. The chain is traversed transitively via BFS. Instance chains can link
   **any combination** of stratigraphic node types (US, USD, SF, VSF, etc.).

Containment Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~

**is_part_of**
^^^^^^^^^^^^^^

:Label: Is Part Of
:Description: Physical containment -- a node is part of a container stratigraphic unit
:CIDOC-CRM: P46_is_composed_of
:Visual Style: Not represented as a visual edge in GraphML (expressed via group nesting)
:Usage: Mereological (part--whole) relationships

.. code-block:: python

   # Special find contained in a wall
   graph.add_edge("part001", "SF10102", "US10101", "is_part_of")

**Allowed Connections:**
   - SpecialFindUnit → StratigraphicUnit
   - SpecialFindUnit → DocumentaryStratigraphicUnit
   - SpecialFindUnit → VirtualSpecialFindUnit
   - VirtualSpecialFindUnit → StratigraphicUnit
   - VirtualSpecialFindUnit → DocumentaryStratigraphicUnit
   - VirtualSpecialFindUnit → VirtualSpecialFindUnit

.. note::
   The reverse edge ``has_part`` is automatically generated by s3dgraphy.
   In the GraphML representation, containment is expressed through **group nodes** --
   the container is a yEd group node with a specific background colour (US: ``#9B3333``,
   USD: ``#D86400``, VSF: ``#B19F61``), and children are placed inside it.

**has_visual_reference**
^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Has Visual Reference
:Description: Links a node to a visual reference document
:CIDOC-CRM: P138i_has_representation
:Visual Style: Solid line
:Usage: Visual documentation links (added in datamodel v1.5.4)

.. code-block:: python

   # Link to visual reference
   graph.add_edge("vis001", "US001", "DOC005_photo", "has_visual_reference")

Documentation Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_data_provenance**
^^^^^^^^^^^^^^^^^^^^^^^

:Label: Data Provenance
:Description: Indicates the provenance of data, often linking to source nodes
:CIDOC-CRM: P70i_is_documented_in
:Visual Style: Dashed line
:Usage: Links interpretations to their sources

.. code-block:: python

   # Property supported by documentation
   graph.add_edge("prov001", "PROP001_material", "DOC001_analysis", "has_data_provenance")

**Allowed Connections:**
   - PropertyNode → DocumentNode
   - PropertyNode → ExtractorNode
   - CombinerNode → ExtractorNode

**extracted_from**
^^^^^^^^^^^^^^^^^^

:Label: Extracted From
:Description: Indicates that information is derived from a particular source
:CIDOC-CRM: P67_refers_to
:Visual Style: Dashed line
:Usage: Information extraction processes

.. code-block:: python

   # Information extracted from document
   graph.add_edge("ext001", "EXT001_typology", "DOC005_corpus", "extracted_from")

**Allowed Connections:**
   - ExtractorNode → DocumentNode
   - PropertyNode → DocumentNode
   - SpecialFindUnit → StratigraphicNode (findspot)

**combines**
^^^^^^^^^^^^

:Label: Combines
:Description: Indicates that a node combines information from various sources
:CIDOC-CRM: P16_used_specific_object
:Visual Style: Dashed line
:Usage: Information synthesis processes

.. code-block:: python

   # Combiner synthesizes multiple sources
   graph.add_edge("comb001", "COMB001_synthesis", "EXT001_dating", "combines")
   graph.add_edge("comb002", "COMB001_synthesis", "EXT002_material", "combines")

**Allowed Connections:**
   - CombinerNode → ExtractorNode
   - CombinerNode → PropertyNode

Property and Attribution Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_property**
^^^^^^^^^^^^^^^^

:Label: Has Property
:Description: Connects a node to one of its properties
:CIDOC-CRM: P2_has_type
:Visual Style: Solid line
:Usage: Attribute assignment

.. code-block:: python

   # Stratigraphic unit has material property
   graph.add_edge("prop001", "US001", "PROP001_material_stone", "has_property")

**Allowed Connections:**
   - StratigraphicNode (and every unit subclass) → PropertyNode
   - EpochNode → PropertyNode
   - GraphNode → PropertyNode
   - DocumentNode / RepresentationModelDocNode → PropertyNode

**contrasts_with**
^^^^^^^^^^^^^^^^^^

:Label: Contrasting Properties
:Description: Represents contrasting or mutually exclusive properties
:CIDOC-CRM: P69_has_association_with
:Visual Style: Dashed-dotted line
:Usage: Alternative interpretations, conflicting evidence

.. code-block:: python

   # Alternative dating interpretations
   graph.add_edge("contrast001", "PROP001_dating_early", "PROP002_dating_late", "contrasts_with")

**Allowed Connections:**
   - PropertyNode → PropertyNode
   - ExtractorNode → ExtractorNode
   - CombinerNode → CombinerNode

Temporal and Epochal Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_first_epoch**
^^^^^^^^^^^^^^^^^^^

:Label: Has First Epoch
:Description: Indicates the initial epoch associated with a node
:CIDOC-CRM: P82a_begin_of_the_begin
:Visual Style: Solid line
:Usage: Temporal assignment to periods

.. code-block:: python

   # Unit belongs to Roman period
   graph.add_edge("epoch001", "US001", "EPOCH_ROMAN", "has_first_epoch")

**Allowed Connections:**
   - StratigraphicNode → EpochNode
   - SpecialFindUnit → EpochNode

**survive_in_epoch**
^^^^^^^^^^^^^^^^^^^^

:Label: Survives In Epoch
:Description: Indicates that a node continues to exist in a given epoch
:CIDOC-CRM: P10_falls_within
:Visual Style: Solid line
:Usage: Long-duration features

.. code-block:: python

   # Wall continues through multiple periods
   graph.add_edge("surv001", "US001_wall", "EPOCH_MEDIEVAL", "survive_in_epoch")

**Allowed Connections:**
   - StratigraphicNode → EpochNode
   - ContinuityNode → EpochNode

Organizational Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**is_in_activity**
^^^^^^^^^^^^^^^^^^

:Label: Part of Activity
:Description: Indicates that a node is part of a specific activity
:CIDOC-CRM: P9_consists_of
:Visual Style: Solid line
:Usage: Activity-based grouping

.. code-block:: python

   # Units part of construction activity
   graph.add_edge("act001", "US001", "ACT001_construction", "is_in_activity")

**Allowed Connections:**
   - Any Node → ActivityNodeGroup

**has_timebranch** / **is_in_timebranch**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Connected to a Timebranch / Included in Timebranch
:Description: Indicates connection to alternative temporal interpretations
:CIDOC-CRM: P67_refers_to
:Visual Style: Solid line
:Usage: Alternative chronological hypotheses

.. code-block:: python

   # Alternative interpretation branch
   graph.add_edge("branch001", "US001", "BRANCH001_early_dating", "has_timebranch")

**Allowed Connections:**
   - Any Node → TimeBranchNodeGroup

**is_in_paradata_nodegroup** / **has_paradata_nodegroup**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Belongs to Paradata Group / Has Paradata Group
:Description: Organizational relationships for paradata management
:CIDOC-CRM: P106_is_composed_of
:Visual Style: Solid line
:Usage: Documentation organization

.. code-block:: python

   # Group paradata by excavation area
   graph.add_edge("para001", "DOC001", "PARAGROUP_AREA_A", "is_in_paradata_nodegroup")

**Allowed Connections:**
   - DocumentNode → ParadataNodeGroup
   - ExtractorNode → ParadataNodeGroup  
   - CombinerNode → ParadataNodeGroup
   - ParadataNodeGroup → ActivityNodeGroup

Specialized Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~

**has_linked_resource**
^^^^^^^^^^^^^^^^^^^^^^^

:Label: Has Link
:Description: Connects a node to its linked resource(s)
:CIDOC-CRM: P67_refers_to
:Visual Style: Solid line
:Usage: External resource links

.. code-block:: python

   # Link to external resource
   graph.add_edge("link001", "US001", "LINK001_3d_model", "has_linked_resource")

**Allowed Connections:**
   - Any Node → LinkNode

**has_semantic_shape**
^^^^^^^^^^^^^^^^^^^^^^

:Label: Has Semantic Shape
:Description: Connects any node to its semantic shape representation in 3D space
:CIDOC-CRM: E36_Visual_Item
:Visual Style: Solid line
:Usage: 3D visualization links

.. code-block:: python

   # Link to 3D semantic representation
   graph.add_edge("shape001", "US001", "SHAPE001_wall_3d", "has_semantic_shape")

**Allowed Connections:**
   - Any Node → SemanticShapeNode

**has_representation_model**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Has Representation Model
:Description: Connects any node to its representation model in 3D space
:CIDOC-CRM: E36_Visual_Item
:Visual Style: Solid line
:Usage: 3D model connections

.. code-block:: python

   # Link to 3D representation model
   graph.add_edge("model001", "US001", "MODEL001_wall", "has_representation_model")

**Allowed Connections:**
   - Any Node → RepresentationModelNode

Licensing and Legal Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_license**
^^^^^^^^^^^^^^^

:Label: Has License
:Description: Indicates that a resource is subject to a specific licence
:CIDOC-CRM: P104_is_subject_to
:Visual Style: Solid line
:Usage: Legal and copyright information

.. code-block:: python

   # Document has specific license
   graph.add_edge("lic001", "DOC001", "LICENSE_CC_BY", "has_license")

**has_embargo**
^^^^^^^^^^^^^^^

:Label: Has Embargo
:Description: Indicates that a licence has an associated time embargo
:CIDOC-CRM: P4_has_time-span
:Visual Style: Solid line
:Usage: Temporal access restrictions

.. code-block:: python

   # License has embargo period
   graph.add_edge("emb001", "LICENSE_CC_BY", "EMBARGO_2025", "has_embargo")

Physical Stratigraphic Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A family of fine-grained physical relations between stratigraphic units,
all backed by ``CRMarchaeo:AP11_has_physical_relation`` and tagged by a
specific ``type_tag`` carried on the edge. Allowed between any two
:class:`StratigraphicNode` instances. **Canonical edges** in this family
(``cuts``, ``fills``, ``overlies``, ``abuts``) ship a named reverse;
**symmetric** edges (``bonded_to``, ``is_bonded_to``,
``is_physically_equal_to``, ``equals``) have ``reverse = None`` and the
exporter emits a single arc.

**cuts**
^^^^^^^^

:Label: Cuts
:Description: This stratigraphic unit cuts the target stratigraphic unit (e.g., a pit cutting a layer).
:CRMarchaeo: AP11_has_physical_relation (``type_tag: cuts``)
:Reverse: ``is_cut_by`` ("Is cut by")
:Allowed Connections: StratigraphicNode → StratigraphicNode

.. code-block:: python

   # Foundation trench cuts an earlier floor
   graph.add_edge("rel_cuts", "US010_trench", "US020_floor", "cuts")

**fills**
^^^^^^^^^

:Label: Fills
:Description: This stratigraphic unit fills the target stratigraphic unit (e.g., a deposit filling a cut).
:CRMarchaeo: AP11_has_physical_relation (``type_tag: fills``)
:Reverse: ``is_filled_by`` ("Is filled by")
:Allowed Connections: StratigraphicNode → StratigraphicNode

**overlies**
^^^^^^^^^^^^

:Label: Overlies
:Description: This stratigraphic unit overlies (covers) the target stratigraphic unit.
:CRMarchaeo: AP11_has_physical_relation (``type_tag: overlies``)
:Reverse: ``is_overlain_by`` ("Is overlain by")
:Allowed Connections: StratigraphicNode → StratigraphicNode

**abuts**
^^^^^^^^^

:Label: Abuts
:Description: This stratigraphic unit abuts against the target stratigraphic unit (e.g., a later wall built against an earlier one).
:CRMarchaeo: AP11_has_physical_relation (``type_tag: abuts``)
:Reverse: ``is_abutted_by`` ("Is abutted by")
:Allowed Connections: StratigraphicNode → StratigraphicNode

**bonded_to** *(symmetric, canonical v5.0 em_data.xlsx)*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Bonded to
:Description: Canonical (v5.0 em_data.xlsx) form of the bonding relation:
   this stratigraphic unit is physically bonded to the target.
   **Symmetric** (``reverse = None``). Allowed between any two
   StratigraphicNode instances, including USVs-USVs when two virtually
   reconstructed elements are theoretically bonded (e.g., two missing
   blocks of the same inferred course).
:CRMarchaeo: AP11_has_physical_relation (``type_tag: bonded to``)
:Reverse: *symmetric — none*
:Allowed Connections: StratigraphicNode → StratigraphicNode

**is_bonded_to** *(symmetric, legacy alias)*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Is bonded to
:Description: Legacy symmetric bonding relation kept alongside the
   canonical ``bonded_to`` for backward compatibility with pre-v5.0
   spreadsheets. New code should prefer ``bonded_to``.
:CRMarchaeo: AP11_has_physical_relation (``type_tag: is bonded to``)
:Reverse: *symmetric — none*

**equals** *(symmetric, canonical v5.0 em_data.xlsx)*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Equals
:Description: Canonical (v5.0 em_data.xlsx) form of the *same physical
   entity* relation: two distinct unit IDs (from different campaigns or
   archival sources) refer to the same stratigraphic fact. Symmetric.
:CRMarchaeo: AP11_has_physical_relation (``type_tag: equals``)
:Reverse: *symmetric — none*

**is_physically_equal_to** *(symmetric, legacy)*
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Is physically equal to
:Description: Two stratigraphic units are considered physically the same
   entity or continuous fabric. Symmetric. Legacy alias of ``equals``.
:CRMarchaeo: AP11_has_physical_relation (``type_tag: equals``)
:Reverse: *symmetric — none*

Spatial / Locational
~~~~~~~~~~~~~~~~~~~~

**is_in_location**
^^^^^^^^^^^^^^^^^^

:Label: Is in location
:Description: Indicates that a node belongs to a spatial / locational
   group (:class:`LocationNodeGroup`). Membership is m:n (multiple
   ``is_in_location`` edges per source are allowed) and **additive**
   (memberships compose; none overrides). The optional ``is_primary``
   attribute on at most one edge per source disambiguates which
   membership is rendered as a yEd group folder in em-graph. The same
   edge type also carries the recursive Location → Location hierarchy
   (Pompei → Sector 4 → Casa del Fauno → Room 12).
:CIDOC-CRM: P53_has_former_or_current_location (node→location) /
   P89_falls_within (location→location, recursive)
:Reverse: ``includes_location`` ("Includes location")
:Edge attribute: ``is_primary: bool`` (default ``false``) — UI hint
:Allowed Connections: StratigraphicNode / ParadataNode /
   ParadataNodeGroup / DocumentNode / ExtractorNode / CombinerNode /
   PropertyNode / LocationNodeGroup → LocationNodeGroup

.. versionadded:: 0.1.41

Geographic / Linked Resource
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_geoposition**
^^^^^^^^^^^^^^^^^^^

:Label: Has geoposition
:Description: Represents a connection with the GeoPositionNode of a given node.
:CIDOC-CRM: P53_has_former_or_current_location
:CRMgeo: Q4_has_spatial_projection
:Reverse: ``is_geoposition_of`` ("Is geoposition of")
:Allowed Connections: StratigraphicNode / ParadataNode /
   RepresentationModelNode / RepresentationModelDocNode /
   RepresentationModelSpecialFindNode → GeoPositionNode

Representation Models
~~~~~~~~~~~~~~~~~~~~~

**has_representation_model_doc**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Has document representation model
:Description: Connects ExtractorNode / DocumentNode / CombinerNode to
   their representation model in 3D space.
:CIDOC-CRM: P138i_has_representation
:Reverse: ``is_doc_representation_model_of``
:Allowed Connections: ExtractorNode / DocumentNode / CombinerNode →
   RepresentationModelDocNode / RepresentationModelSpecialFindNode

**has_representation_model_sf**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Has special find representation model
:Description: Connects SpecialFindUnit nodes to their representation
   model in 3D space.
:CIDOC-CRM: P138i_has_representation
:Reverse: ``is_sf_representation_model_of``
:Allowed Connections: SpecialFindUnit → RepresentationModelSpecialFindNode

Documentation (extended)
~~~~~~~~~~~~~~~~~~~~~~~~

**has_documentation**
^^^^^^^^^^^^^^^^^^^^^

:Label: Has documentation
:Description: Indicates that the element has an associated documentation node.
:CIDOC-CRM: P104_is_subject_to
:Reverse: ``is_documentation_of`` ("Is documentation of")
:Allowed Connections: StratigraphicNode / SpecialFindUnit /
   VirtualStratigraphicUnit → DocumentNode

Paradata Group Reverses
~~~~~~~~~~~~~~~~~~~~~~~

**is_in_paradata_nodegroup**
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:Label: Is in paradata nodegroup
:Description: Membership of a node inside a ParadataNodeGroup. Canonical
   form (source → group) with reverse ``contains_paradata_node``.
:CIDOC-CRM: P106_is_composed_of
:Reverse: ``contains_paradata_node`` ("Contains paradata node")
:Allowed Connections: PropertyNode / DocumentNode / ExtractorNode /
   CombinerNode / ParadataNode → ParadataNodeGroup

Authorship
~~~~~~~~~~

**has_author**
^^^^^^^^^^^^^^

:Label: Has author
:Description: Represents the connection of a node with its author. Target
   can be an :class:`AuthorNode` (human) or :class:`AuthorAINode`
   (AI-assisted authoring). Source covers the full range of EM node types
   so that the resolver can walk from any scope level down to the author.
:CIDOC-CRM: P94_has_created
:CRMdig: L10_had_input
:Reverse: ``is_author_of`` ("Is author of")
:Allowed Connections: GraphNode / StratigraphicNode / ParadataNode /
   GroupNode / DocumentNode / ExtractorNode / CombinerNode / PropertyNode /
   EpochNode → AuthorNode / AuthorAINode

.. note::

   Author resolution is multi-valued: every ``has_author`` edge from the
   source is followed and their display names are joined with ``" ; "``.
   See :doc:`/internals/propagation` for the node-level → swimlane-level
   fallback order used by ``AUTHOR_RULE``.

Time-branch reverses
~~~~~~~~~~~~~~~~~~~~

**has_timebranch**
^^^^^^^^^^^^^^^^^^

:Label: Has timebranch
:Description: Connects a node to a specific TimeBranchNodeGroup
   (alternative temporal interpretation).
:CIDOC-CRM: P67_refers_to
:CRMem: em:belongsToAlternative
:Reverse: ``is_timebranch_of`` ("Is timebranch of")
:Allowed Connections: StratigraphicNode → TimeBranchNodeGroup

Complete Reverse Reference
--------------------------

The following table lists the **30 distinct reverse names** computed by
:meth:`Edge.get_reverse_name`. Each row is the reverse of the canonical
edge in the right column. Use the canonical name when constructing edges
with :meth:`Graph.add_edge`; the reverse is for UI labels and queries
only.

==================================  ==========================
Reverse name                         Canonical
==================================  ==========================
``is_before``                        ``is_after``
``changed_to``                       ``changed_from``
``is_cut_by``                        ``cuts``
``is_filled_by``                     ``fills``
``is_overlain_by``                   ``overlies``
``is_abutted_by``                    ``abuts``
``has_part``                         ``is_part_of``
``is_data_provenance_of``            ``has_data_provenance``
``is_source_for_extraction``         ``extracted_from``
``is_combined_by``                   ``combines``
``is_property_of``                   ``has_property``
``is_first_epoch_of``                ``has_first_epoch``
``contains_surviving``               ``survive_in_epoch``
``includes_in_activity``             ``is_in_activity``
``includes_location``                ``is_in_location``
``contains_paradata_node``           ``is_in_paradata_nodegroup``
``is_paradata_nodegroup_of``         ``has_paradata_nodegroup``
``contains_in_timebranch``           ``is_in_timebranch``
``is_timebranch_of``                 ``has_timebranch``
``is_author_of``                     ``has_author``
``is_geoposition_of``                ``has_geoposition``
``is_linked_resource_of``            ``has_linked_resource``
``is_representation_model_of``       ``has_representation_model``
``is_doc_representation_model_of``   ``has_representation_model_doc``
``is_sf_representation_model_of``    ``has_representation_model_sf``
``is_semantic_shape_of``             ``has_semantic_shape``
``is_documentation_of``              ``has_documentation``
``is_visual_reference_of``           ``has_visual_reference``
``is_license_of``                    ``has_license``
``is_embargo_of``                    ``has_embargo``
==================================  ==========================

Symmetric edges (no reverse): ``bonded_to``, ``is_bonded_to``,
``equals``, ``is_physically_equal_to``, ``has_same_time``,
``contrasts_with``, ``generic_connection``.

Generic Relationships
~~~~~~~~~~~~~~~~~~~~~

**generic_connection**
^^^^^^^^^^^^^^^^^^^^^^

:Label: Generic Connection
:Description: Represents a non-specific connection between two nodes
:CIDOC-CRM: P67_refers_to
:Visual Style: Solid line
:Usage: Placeholder for unspecified relationships

.. code-block:: python

   # Generic connection (should be enhanced to specific type)
   graph.add_edge("gen001", "NODE001", "NODE002", "generic_connection")

**Note:** Generic connections are often enhanced to more specific types during import processing.

Connection Validation Rules
---------------------------

Node Type Compatibility Matrix
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

s3dgraphy enforces strict validation rules for edge connections based on archaeological logic:

.. code-block:: python

   # Validation example
   source_node = graph.find_node_by_id("US001")
   target_node = graph.find_node_by_id("DOC001")
   
   if Graph.validate_connection(source_node.node_type, target_node.node_type, "has_data_provenance"):
       graph.add_edge("valid_edge", "US001", "DOC001", "has_data_provenance")
   else:
       print("Invalid connection type")

**Common Valid Patterns:**

Stratigraphic Relationships
^^^^^^^^^^^^^^^^^^^^^^^^^^^
   - US → US (is_before, has_same_time)
   - US → SF (extracted_from - findspot)
   - US → EpochNode (has_first_epoch, survive_in_epoch)

Documentation Chains
^^^^^^^^^^^^^^^^^^^^
   - DocumentNode → ExtractorNode (extracted_from)
   - ExtractorNode → CombinerNode (combines)
   - PropertyNode → DocumentNode (has_data_provenance)
   - US/SF → PropertyNode (has_property)

Organizational Structures
^^^^^^^^^^^^^^^^^^^^^^^^^
   - Any Node → ActivityNodeGroup (is_in_activity)
   - ParadataNode → ParadataNodeGroup (is_in_paradata_nodegroup)
   - Any Node → TimeBranchNodeGroup (has_timebranch)

Best Practices for Edge Usage
-----------------------------

Temporal Relationships
~~~~~~~~~~~~~~~~~~~~~~

1. **Use consistent direction**: Later units point to earlier units with "is_after" (canonical direction from recent to ancient)
2. **Document contemporaneity**: Use "has_same_time" for features built together
3. **Model transformations**: Use "changed_from" for reuse and modification

.. code-block:: python

   # Good: Consistent temporal direction (canonical "is_after")
   graph.add_edge("temp1", "US002_wall", "US003_foundation", "is_after")  # wall is more recent than foundation
   graph.add_edge("temp2", "US001_roof", "US002_wall", "is_after")  # roof is more recent than wall
   
   # Good: Contemporary features
   graph.add_edge("cont1", "US002_wall", "US004_floor", "has_same_time")

Documentation Chains
~~~~~~~~~~~~~~~~~~~~

1. **Complete paradata chains**: Link properties through extractors to documents
2. **Use specific edge types**: Avoid generic_connection when possible
3. **Document conflicting interpretations**: Use contrasts_with for alternatives

.. code-block:: python

   # Complete documentation chain
   graph.add_edge("prop1", "US001", "PROP001_material", "has_property")
   graph.add_edge("ext1", "EXT001_analysis", "DOC001_lab_report", "extracted_from") 
   graph.add_edge("prov1", "PROP001_material", "EXT001_analysis", "has_data_provenance")

Organizational Structure
~~~~~~~~~~~~~~~~~~~~~~~~

1. **Group related elements**: Use node groups for logical organization
2. **Separate activity phases**: Use activity groups for excavation phases
3. **Model alternative interpretations**: Use time branches for competing hypotheses

.. code-block:: python

   # Organizational grouping
   graph.add_edge("org1", "US001", "ACT001_phase1", "is_in_activity")
   graph.add_edge("org2", "DOC001", "PARA001_area_a", "is_in_paradata_nodegroup")

Error Handling and Validation
-----------------------------

Common Edge Validation Errors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Invalid Node Types**
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # This will fail validation
   try:
       graph.add_edge("invalid", "US001", "US002", "has_license")
   except ValueError as e:
       print(f"Invalid connection: {e}")
       # US nodes cannot have license relationships

**Missing Nodes**
^^^^^^^^^^^^^^^^^

.. code-block:: python

   # Check nodes exist before creating edges
   if (graph.find_node_by_id("US001") and 
       graph.find_node_by_id("US002")):
       graph.add_edge("rel1", "US001", "US002", "is_before")
   else:
       graph.add_warning("Cannot create edge: missing nodes")

**Circular Dependencies**
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   # Detect circular temporal relationships
   def check_temporal_cycles(graph):
       temporal_edges = [e for e in graph.edges if e.edge_type == "is_before"]
       # Implementation of cycle detection algorithm
       return has_cycles

Edge Enhancement During Import
------------------------------

GraphML Import Processing
~~~~~~~~~~~~~~~~~~~~~~~~~

The GraphMLImporter automatically enhances edge types based on connected node types:

.. code-block:: python

   def enhance_edge_type(self, source_node, target_node, edge_type):
       """Enhance generic connections to specific types"""
       
       if edge_type == "generic_connection":
           # DocumentNode → ExtractorNode becomes "extracted_from"
           if (source_node.node_type == "document" and 
               target_node.node_type == "extractor"):
               return "extracted_from"
           
           # ExtractorNode → CombinerNode becomes "combines"  
           elif (source_node.node_type == "extractor" and
                 target_node.node_type == "combiner"):
               return "combines"
       
       return edge_type

Export Considerations
---------------------

GraphML Export
~~~~~~~~~~~~~~

Edge types are preserved with their semantic meaning and visual styling:

.. code-block:: python

   # Export preserves edge semantics
   exporter = GraphMLExporter()
   exporter.export_graph(graph, "output.graphml", 
                        preserve_edge_styles=True)

JSON Export
~~~~~~~~~~~

Edges include full metadata and CIDOC-CRM mappings:

.. code-block:: python

   # JSON export includes semantic information
   {
       "edge_id": "rel001",
       "source": "US001", 
       "target": "US002",
       "edge_type": "is_before",
       "label": "Chronological Sequence",
       "description": "Indicates a temporal sequence where one item occurs before another",
       "cidoc_mapping": "P120_occurs_before",
       "visual_style": "solid_line"
   }

This comprehensive edge reference provides the foundation for creating semantically rich archaeological graphs in s3dgraphy.
