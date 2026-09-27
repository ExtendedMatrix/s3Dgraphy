Core Concepts
=============

This section introduces the fundamental concepts and architecture of s3dgraphy,
the core Python library implementing the Extended Matrix formal language.

Graph Structure
---------------

s3dgraphy implements a **property graph model** specifically designed for archaeological
stratigraphic documentation. Each graph represents an archaeological site or project
and contains:

**Nodes (Vertices)**
   Represent archaeological entities such as stratigraphic units, documents,
   interpretations, and metadata

**Edges (Relationships)**
   Represent relationships between entities, including temporal sequences,
   documentation links, containment, and analytical connections

**Properties**
   Both nodes and edges can carry attributes and metadata specific to
   archaeological documentation needs

Multigraph Architecture
-----------------------

s3dgraphy supports **multiple graphs** within a single project through the
MultiGraphManager system:

.. code-block:: python

   from s3dgraphy import MultiGraphManager

   # Access the global manager
   manager = MultiGraphManager()

   # Create multiple site graphs
   site_a = manager.create_graph("SiteA_2024")
   site_b = manager.create_graph("SiteB_2024")

   # Each graph is independent but can reference others
   print(f"Active graphs: {manager.get_all_graph_ids()}")

This allows for:

- **Multi-site projects** with separate but related documentation
- **Temporal phases** of the same site across different excavation seasons
- **Alternative hypotheses** represented as separate graph variants
- **Data organization** by research team or institutional affiliation

Node Type Hierarchy
--------------------

s3dgraphy implements a specialized node type system for archaeological documentation.
All node classes inherit from a common ``Node`` base class and are auto-registered
via ``__init_subclass__()``, enabling automatic type dispatch during import.

Stratigraphic Nodes
~~~~~~~~~~~~~~~~~~~~

These are the core archaeological units:

**StratigraphicUnit (US)**
   Physical stratigraphic units -- walls, floors, fills, deposits. Can also act as
   a *container* for Special Finds via ``is_part_of`` edges (see :ref:`containers`).

**SeriesOfStratigraphicUnit (serSU)**
   A single node representing multiple serial elements of the same type (e.g., a
   sequence of capitals, column bases) that are geometrically discontinuous.

**DocumentaryStratigraphicUnit (USD)**
   Units identified through indirect documentation -- historical records, geophysical
   surveys, photographs, paintings, written descriptions. Can also act as a *container*.

**SeriesOfDocumentaryStratigraphicUnit (serUSD)**
   Serial variant of USD for groups of documentary units sharing similar characteristics.

**StructuralVirtualStratigraphicUnit (USV/s)**
   Virtual reconstruction hypothesis based on an in-situ fragmented SU. Restores the
   effect of a destruction event, making the reconstruction "physically proven."

**NonStructuralVirtualStratigraphicUnit (USV/n)**
   Virtual reconstruction based on external sources (comparisons, general rules).
   Not connected to a destruction event, hence not "physically proven."

**SeriesOfNonStructuralVirtualStratigraphicUnit (serUSVn)**
   Series of USV/n objects (e.g., a colonnade), considered as a whole.

**SpecialFindUnit (SF)**
   A non-in-situ element (fragmented or intact) that needs repositioning. It is a real
   object with known properties except for original position.

**VirtualSpecialFindUnit (VSF)**
   Represents restoration, integration, or completion of a repositioned SF. Inherits
   physical properties from the corresponding SF. Can also act as a *container* for
   SF elements that compose it (e.g., tile fragments belonging to a reconstructed roof).

**TransformationStratigraphicUnit (TSU)**
   Records chemical, physical, or biological changes on a surface or material over time.
   Subtypes: colour change, negative/subtractive, positive/additive, translational.

**ContinuityNode**
   A technical node that marks the survival of a stratigraphic unit into a subsequent
   epoch without physical change.

**StratigraphicEventNode**
   Represents a destruction event (negative SU, prefixed with ``-``).

Paradata Nodes
~~~~~~~~~~~~~~

Documentation and data provenance nodes forming the paradata chain:

**DocumentNode (DOC)**
   Source materials -- photos, drawings, reports, 3D scans, historical texts.

**ExtractorNode (EXT)**
   Information extraction processes -- how data was derived from a source.

**CombinerNode (COMB)**
   Information combination/reasoning -- synthesising multiple extracted data points.

**PropertyNode (PROP)**
   Properties associated with stratigraphic nodes -- material, colour, dating, etc.

**AuthorNode (AUTH)**
   Persons responsible for documentation or interpretation.

Group Nodes
~~~~~~~~~~~

Organizational containers used in the Extended Matrix graph:

**ParadataNodeGroup**
   Groups paradata nodes (DOC, EXT, COMB) together as a documentation unit for a
   stratigraphic node.

**ActivityNodeGroup**
   Archaeological activities or events that group related stratigraphic units.

**TimeBranchNodeGroup**
   Alternative temporal sequences -- branches representing competing hypotheses
   about the chronological interpretation of a site.

Representation Nodes
~~~~~~~~~~~~~~~~~~~~

3D model and visualization metadata:

**RepresentationModelNode**
   3D model associated with a stratigraphic unit (glTF/GLB format).

**RepresentationModelDocNode**
   3D model of a documentation source (e.g., photogrammetric model).

**RepresentationModelSpecialFindNode**
   3D model of a special find.

**SemanticShapeNode**
   Symbolic 3D shapes (proxies, annotations in 3D space).

Reference Nodes
~~~~~~~~~~~~~~~

**EpochNode (EP)**
   Temporal periods and chronological frameworks with start/end dates.

**GeoPositionNode (GEO)**
   Spatial reference systems and coordinates (EPSG, shifts).

**LinkNode (LINK)**
   External resource links.

**LicenseNode / EmbargoNode**
   Rights management and temporal access restrictions.

Edge Types and Relationships
-----------------------------

s3dgraphy uses **semantic edge types** that correspond to specific archaeological
relationships and CIDOC-CRM ontology mappings. In the GraphML representation, edge
types are encoded as visual line styles; during import, they are converted to their
semantic names.

.. _canonical-vs-reverse-edges-core:

Canonical, Reverse, and Symmetric Edges (v1.5.3+)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Since connections datamodel **v1.5.3**, every directed edge in s3dgraphy
is registered under a **single canonical name**. The reverse direction
has its own *display name* but is **not** a separate edge type — it is
computed on demand from the JSON datamodel via
:meth:`Edge.get_reverse_name`. Three categories exist:

**Canonical edges** (the registered name)
   :meth:`Graph.add_edge` requires the canonical name. Examples:
   ``is_after`` (canonical for the temporal sequence pair),
   ``cuts`` (canonical for the cuts/is_cut_by pair),
   ``has_property`` (canonical for the property attachment pair).

**Reverse edges** (a display name only)
   Returned by :meth:`Edge.get_reverse_name` for UI labels in node
   editors. Examples: ``is_before`` (reverse of ``is_after``),
   ``is_cut_by`` (reverse of ``cuts``), ``is_property_of`` (reverse of
   ``has_property``).

**Symmetric edges** (``reverse = None``)
   Direction is meaningless. The exporter emits a single arc with no
   implicit reverse. Set: ``bonded_to``, ``equals``, ``has_same_time``,
   ``contrasts_with``, ``generic_connection`` — plus ``is_bonded_to`` and
   ``is_physically_equal_to``, which are not relations of their own but
   older spellings of ``bonded_to`` and ``equals`` (``spelling_of`` in the
   datamodel: read, never written).

Why the schema change matters:

- The :class:`~s3dgraphy.exporter.unified_xlsx_exporter.UnifiedXLSXExporter`
  emits only the *canonical* direction (``overlies``, not
  ``is_overlain_by``) — the inverse is recovered at re-import, so the
  workbook stays deduplicated.
- Node editors (yEd, em-graph) label sockets with the appropriate verb
  by calling :meth:`Edge.get_reverse_name` — no re-implementation of
  the lookup table per editor.
- The ``PHYSICAL_STRATIGRAPHIC_TYPES`` family (``cuts``, ``fills``,
  ``overlies``, ``abuts``) follows the same convention; the reverses
  (``is_cut_by``, ``is_filled_by``, ``is_overlain_by``,
  ``is_abutted_by``) all map back to the canonical via the JSON
  datamodel.

The number of canonical edge types and of distinct reverse names is not
written out here: it moves with the datamodel and a copied figure goes
stale. See :doc:`generated-report` for the current counts, and
:ref:`canonical-reverse-edges` in the edges reference for the full
per-edge listing.

Migration from pre-1.5.3 code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pre-1.5.3 code that constructed reverse-direction edges directly
(``graph.add_edge(_, _, _, "is_before")``) will fail
:meth:`Graph.add_edge` validation. Migrate to the canonical
direction (``"is_after"``) and let the consumer call
:meth:`Edge.get_reverse_name` for UI labels.

Edge style mapping (GraphML)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the GraphML representation:

.. list-table:: GraphML Line Style to Semantic Edge Type Mapping
   :header-rows: 1
   :widths: 25 25 50

   * - **GraphML Line Style**
     - **Semantic Edge Type**
     - **Meaning**
   * - solid line
     - ``is_after`` / ``is_before``
     - Chronological sequence between stratigraphic units
   * - double line
     - ``has_same_time``
     - Contemporaneous elements
   * - dotted line
     - ``changed_from``
     - Same object across epochs (instance chain)
   * - dashed line
     - ``has_data_provenance``
     - Provenance and documentation relationships
   * - dashed-dotted line
     - ``contrasts_with``
     - Conflicting hypotheses or mutually exclusive branches

Temporal Relationships
~~~~~~~~~~~~~~~~~~~~~~

**is_after / is_before**
   Chronological sequence between stratigraphic units. The canonical direction in the
   Extended Matrix is from more recent to more ancient (``is_after``).

**has_same_time**
   Two elements are contemporaneous -- they existed or were created at the same time.

**changed_from**
   Represents the same physical object through different epochs. When multiple nodes
   are connected by ``changed_from`` edges, they form an **instance chain** -- a
   navigable sequence documenting the complete biography of a single object through time.

   Example: a capital found on the ground today (SF), the same capital as a collapsed
   element in a previous epoch (USD), and the capital in its original Roman-era position
   (US) form a three-node instance chain.

Containment Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~

**is_part_of / has_part**
   Mereological (part--whole) relationships. A child node ``is_part_of`` a container
   node. The reverse ``has_part`` is automatically generated.

   Allowed sources: SF, VSF.
   Allowed targets: US, USD, VSF.

   In GraphML, containment is expressed through group nodes with specific background
   colours. See :ref:`containers` below.

Documentation Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_data_provenance**
   Links interpretations to their evidence sources.

**extracted_from**
   Information derived from a specific document or source.

**combines**
   Synthesised from multiple sources via a CombinerNode.

**has_property**
   Associates a PropertyNode (material, colour, dating, etc.) with a stratigraphic node.

Group Relationships
~~~~~~~~~~~~~~~~~~~

**has_first_epoch / survive_in_epoch**
   Connect stratigraphic units to their temporal periods.

**is_in_activity / has_activity**
   Group related units under a common activity or event.

**has_timebranch / is_in_timebranch**
   Connect nodes to alternative interpretation branches.

**contrasts_with**
   Marks two time branches as mutually exclusive.

Representation Relationships
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**has_representation_model**
   Links a stratigraphic node to its 3D model.

**has_visual_reference**
   Links a node to a visual reference (added in datamodel v1.5.4).

**has_semantic_shape**
   Links a node to a symbolic 3D shape.

.. _containers:

Container Group Nodes
---------------------

In the Extended Matrix, certain stratigraphic units can act as **containers** for
other elements. This expresses a mereological (part--whole) relationship: a Special
Find (SF) is physically contained within a wall (US), or fragments (SF) compose a
reconstructed whole (VSF).

**How it works in yEd:**

In the yEd graph editor, a container is represented as a **group node** with a
specific background colour. Child elements are placed visually inside the group.

.. list-table:: Container Group Node Colours
   :header-rows: 1
   :widths: 30 20 50

   * - **Container Type**
     - **Background Colour**
     - **Example**
   * - US (Stratigraphic Unit)
     - ``#9B3333`` (dark red)
     - A wall containing a reused capital (SF)
   * - USD (Documentary Strat. Unit)
     - ``#D86400`` (orange)
     - A documentary context containing an artefact (SF)
   * - VSF (Virtual Special Find)
     - ``#B19F61`` (gold)
     - A reconstructed roof containing tile fragments (SF)

**How it works in s3dgraphy:**

During GraphML import, the importer:

1. Detects group nodes with the recognised background colours
2. Creates a regular stratigraphic node of the appropriate type (not a GroupNode subclass)
3. Creates ``is_part_of`` edges from each child node to the container
4. The container retains all its normal stratigraphic relationships (epoch, activity, temporal edges)

The container is identified at query time by the presence of ``is_part_of`` / ``has_part``
edges, not by a special node class.

During GraphML export, container nodes are re-exported as group nodes with the correct
background colours, preserving the visual nesting in yEd.

Instance Chains
---------------

When the same physical object exists across multiple epochs -- each represented as a
distinct stratigraphic unit -- the ``changed_from`` connector links these instances
into a navigable **instance chain**.

The chain is traversed transitively: if A ``changed_from`` B and B ``changed_from`` C,
then A, B, and C form a single instance chain representing the complete biography of
a physical object through time.

**Naming convention** (recommended but not enforced):

``{TYPE}{ID}-{LETTER}`` where the letter indicates the epoch order (A = most recent,
B = previous, C = older, etc.). Example: ``USM5000-A``, ``USD5000-B``, ``SF5000-C``.

The system relies solely on ``changed_from`` edges to identify chains, never on name parsing.

In the EM-tools Blender interface, instance chain members are marked with a three-dots
icon and can be filtered to show only the chain members.

Comment Node Skipping
---------------------

yEd allows users to place annotation/comment nodes in their graphs. These are typically
yellow rectangular nodes used for notes and are not part of the archaeological data model.

During GraphML import, s3dgraphy automatically detects and skips nodes with the following
fill colours:

- ``#FFCC00``
- ``#FFFF00``
- ``#FFFF99``

These nodes are silently excluded from the graph and a log message is printed.

Chronology Calculation
----------------------

s3dgraphy includes a built-in **chronology calculation engine** that infers absolute
date ranges for every stratigraphic node in the graph. The algorithm combines three
sources of temporal information:

1. **Absolute dates** from PropertyNodes (``absolute_time_start``,
   ``absolute_time_end``) connected via ``has_property`` edges
2. **Epoch membership** from ``has_first_epoch`` / ``survive_in_epoch`` edges, which
   provide fallback date ranges from EpochNode start/end values
3. **Stratigraphic relations** (``is_after`` / ``is_before``), which constrain the
   possible date range of each node through BFS propagation

The result is a pair of computed attributes on each node:

- ``CALCUL_START_T`` — the **Terminus Post Quem (TPQ)**: the earliest possible start
  date, constrained by predecessors
- ``CALCUL_END_T`` — the **Terminus Ante Quem (TAQ)**: the latest possible end date,
  constrained by successors

**Example:** If ``USV132`` is stratigraphically *after* ``VSF141``, and ``VSF141``
has ``absolute_time_start = 180``, then ``USV132``'s ``CALCUL_START_T`` will be at
least 180, because it cannot have been created before the unit it sits on top of.

This chronology data is used by EM-tools to:

- Colorize 3D models by temporal horizon in **Visual Manager**
- Filter stratigraphic lists by horizon time range in **Stratigraphy Manager**
- Synchronize RM (Representation Model) visibility with horizon ranges

CIDOC-CRM Mapping
------------------

s3dgraphy maintains compatibility with the CIDOC-CRM ontology for heritage data
interoperability. Each node type and edge type carries CIDOC-CRM mapping metadata,
including extensions:

.. list-table:: Key Edge Type CIDOC-CRM Mappings
   :header-rows: 1
   :widths: 25 35 40

   * - **Edge Type**
     - **CIDOC-CRM Property**
     - **Archaeological Meaning**
   * - is_before
     - P120_occurs_before
     - Chronological sequence of stratigraphic events
   * - has_same_time
     - P114_is_equal_in_time_to
     - Contemporary elements or features
   * - changed_from
     - P123_resulted_from
     - Same object across epochs (instance chain)
   * - has_data_provenance
     - P70i_is_documented_in
     - Provenance and documentation relationships
   * - contrasts_with
     - P69_has_association_with
     - Mutually exclusive interpretations
   * - is_part_of
     - P46_is_composed_of
     - Mereological containment (part--whole)
   * - has_property
     - P2_has_type
     - Property attribution

For complete CIDOC-CRM mappings, see the connections datamodel JSON configuration
(:doc:`s3dgraphy_json_config`).

Integration with Extended Matrix Framework
------------------------------------------

s3dgraphy serves as the core library for the broader Extended Matrix ecosystem:

**EMtools for Blender**
   3D visualization and interactive annotation of stratigraphic units

**3D Survey Collection (3DSC)**
   High-quality 3D model preparation and metadata management

**ATON 3 Framework**
   Web-based archaeological visualization and data sharing

**Heriverse Platform**
   Virtual heritage experiences and public engagement

The library's design ensures seamless data flow between these tools while maintaining
scientific rigor and documentation standards.

Performance and Scalability
----------------------------

s3dgraphy is optimized for real-world archaeological projects:

**Graph Size Support**
   - **Small projects**: 100-500 nodes (single-season excavations)
   - **Medium projects**: 500-5,000 nodes (multi-season sites)
   - **Large projects**: 5,000+ nodes (major archaeological sites)

**Performance Optimization**
   - Indexed node and edge lookups via ``GraphIndices``
   - O(1) node lookup by ID, type, and name
   - Optimized graph traversal algorithms
   - Lazy index invalidation for batch operations
