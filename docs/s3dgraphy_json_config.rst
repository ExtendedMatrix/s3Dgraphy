JSON Configuration Files
========================

s3dgraphy uses three core JSON configuration files that define the Extended Matrix data model. These files are loaded automatically when s3dgraphy is imported and provide the foundation for node types, edge types, visual rules, and CIDOC-CRM mappings.

.. note::
   Configuration files are located in: ``src/s3dgraphy/JSON_config/``

Core Configuration Files
------------------------

s3dgraphy includes three essential JSON configuration files:

1. **s3Dgraphy_node_datamodel.json** - Defines all node types and their properties
2. **s3Dgraphy_connections_datamodel.json** - Defines all edge types with CIDOC-CRM mappings  
3. **em_visual_rules.json** - Defines visual representation rules for Blender

Node Data Model
---------------

File: ``s3Dgraphy_node_datamodel.json``

Version: see :doc:`generated-report`, which reads it off the file at build time.

This file defines all node types available in the Extended Matrix, organized into categories.

Structure Overview
~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "s3Dgraphy_node_model_version": "1.5.1",
       "description": "Complete node type definitions for Extended Matrix",
       "node_categories": {
           "stratigraphic_nodes": { ... },
           "paradata_nodes": { ... },
           "group_nodes": { ... },
           "representation_nodes": { ... },
           "reference_nodes": { ... },
           "rights_nodes": { ... },
           "fallback_nodes": { ... }
       }
   }

Node Categories
~~~~~~~~~~~~~~~

Stratigraphic Nodes
^^^^^^^^^^^^^^^^^^^

Physical and virtual archaeological units:

**StratigraphicUnit (US)**
   Physical stratigraphic units (walls, floors, fills, etc.)
   
   - CIDOC-CRM: ``A2 Stratigraphic Volume Unit``
   - CRMarchaeo: ``A1 Excavation Process Unit``
   - Abbreviation: ``US``

.. sync: manual

**Virtual stratigraphic units (USVs · USVn · USD)**
   Units that are *not* physically observed and are argued to have been there.
   There is no single ``USV`` type: the datamodel declares the three kinds
   separately, and the abstract parent lives in the ontology.
   
   - Types: ``USVs`` (structural), ``USVn`` (non-structural), ``USD`` (documentary)
   - CRMem: ``em:StructuralVirtualSU``, ``em:NonStructuralVirtualSU``,
     ``em:DocumentaryVirtualSU``, all beneath ``em:VirtualSU``
   - CIDOC-CRM: ``crmarchaeo:A8_Stratigraphic_Unit`` **and**
     ``crminf:I4_Proposition_Set`` — both, which is the point: see :doc:`crmem`
   - Not ``A2_Stratigraphic_Volume_Unit``: A2 is a physical volume and a virtual
     unit has none

**SpecialFindUnit (SF)**
   Physical special finds (artifacts, samples)
   
   - CIDOC-CRM: ``E19 Physical Object``
   - Abbreviation: ``SF``

**VirtualSpecialFindUnit (VSF)**
   Virtual special finds (reconstructed artifacts)
   
   - CIDOC-CRM: ``E89 Propositional Object``
   - Abbreviation: ``VSF``

**DocumentaryStratigraphicUnit (USD)**
   Units known only from historical documents
   
   - CIDOC-CRM: ``A8 Stratigraphic Unit``
   - Abbreviation: ``USD``

Paradata Nodes
^^^^^^^^^^^^^^

Documentation and data provenance nodes:

**ParadataNode** (Base class)
   Base for all documentation nodes
   
   - CIDOC-CRM: ``A8 Stratigraphic Unit``

**PropertyNode (PROP)**
   Properties associated with stratigraphic nodes
   
   - CIDOC-CRM: ``E1 CRM Entity``
   - Attributes: ``value``, ``property_type``

**DocumentNode (DOC)**
   Documentation sources (photos, drawings, reports)
   
   - CIDOC-CRM: ``E31 Document``
   - Supports: Images, PDFs, 3D models, technical drawings

**ExtractorNode (EXT)**
   Information extraction processes
   
   - CIDOC-CRM: ``crminf:I7_Belief_Adoption``
   - Attributes: ``source``, ``method``

**CombinerNode (COMB)**
   Information combination/reasoning processes
   
   - CIDOC-CRM: ``crminf:I5_Inference_Making``
   - Attributes: ``sources``

Group Nodes
^^^^^^^^^^^

Organizational grouping nodes:

**ParadataNodeGroup**
   Groups paradata nodes together
   
   - CIDOC-CRM: ``E89 Propositional Object``

**TimeBranchNodeGroup**
   Alternative temporal sequences
   
   - CIDOC-CRM: ``E4 Period``

**ActivityNodeGroup**
   Archaeological activities/events
   
   - CIDOC-CRM: ``E7 Activity``
   - CRMarchaeo: ``A3 Stratigraphic Modification``

Representation Nodes
^^^^^^^^^^^^^^^^^^^^

3D model and visualization nodes:

**RepresentationModelNode**
   3D models of stratigraphic units
   
   - CIDOC-CRM: ``D1 Digital Object``
   - Formats: glTF, OBJ, PLY

**RepresentationModelDocNode**
   3D models of documentation (photogrammetry, etc.)
   
   - CIDOC-CRM: ``D1 Digital Object``

**RepresentationModelSpecialFindNode**
   3D models of special finds
   
   - CIDOC-CRM: ``D1 Digital Object``

**SemanticShapeNode**
   Symbolic 3D shapes (proxies, annotations)
   
   - CIDOC-CRM: ``E73 Information Object``
   - Supports: Convex shapes, spheres

Reference Nodes
^^^^^^^^^^^^^^^

Geographic and linking nodes:

**GeoPositionNode (GEO)**
   Geographic position data
   
   - CIDOC-CRM: ``E53 Place``
   - CRMgeo: ``SP5 Geometric Place Expression``
   - Attributes: ``epsg``, ``shift_x``, ``shift_y``, ``shift_z``

**EpochNode (EP)**
   Temporal periods/phases
   
   - CIDOC-CRM: ``E4 Period``
   - Attributes: ``start_date``, ``end_date``

Rights Nodes
^^^^^^^^^^^^

Author and licensing nodes:

**AuthorNode (AUTH)**
   Author/creator information
   
   - CIDOC-CRM: ``E21 Person``
   - Attributes: ``name``, ``surname``, ``orcid``

**LicenseNode**
   Licensing information
   
   - CIDOC-CRM: ``E30 Right``

**EmbargoNode**
   Temporal embargo on data
   
   - CIDOC-CRM: ``E30 Right``

Fallback Nodes
^^^^^^^^^^^^^^

**UnknownNode (UNK)**
   Fallback for unrecognized node types
   
   - CIDOC-CRM: ``E1 CRM Entity``
   - Used only for error handling

Node Definition Structure
~~~~~~~~~~~~~~~~~~~~~~~~~

Each node type has this structure:

.. code-block:: json

   {
       "StratigraphicUnit": {
           "class": "StratigraphicUnit",
           "parent": "Node",
           "abbreviation": "US",
           "label": "Stratigraphic Unit",
           "description": "Physical stratigraphic unit",
           "s3Dgraphy_file": "stratigraphic_node.py",
           "mapping": {
               "cidoc": "E18 Physical Thing",
               "cidoc_s3d": "StratigraphicUnit",
               "alternative": "A1 Excavation Process Unit"
           },
           "properties": {
               "name": "P1_is_identified_by",
               "description": "P3_has_note",
               "material": "P45_consists_of",
               "dating": "P4_has_time-span"
           }
       }
   }

Connections Data Model
----------------------

File: ``s3Dgraphy_connections_datamodel.json``

Version: see :doc:`generated-report`, which reads it off the file at build time.

This file defines all edge types (connections) with CIDOC-CRM mappings.

CIDOC-CRM Extensions
~~~~~~~~~~~~~~~~~~~~

The connections model includes mappings to:

- **CIDOC-CRM** - Core ontology
- **CRMarchaeo** - Archaeological extension
- **CRMsci** - Scientific observation extension
- **CRMdig** - Digital provenance extension
- **CRMgeo** - Geographic extension
- **CRMinf** - Argumentation extension
- **CRMem** - Extended Matrix custom extension (formerly *CIDOC-S3D*; formal draft = the ``em:`` namespace in ``em.ttl``. The per-type ``CIDOC-S3D:`` strings listed on this page document the legacy v1.5 ``cidoc_s3d`` field, superseded in datamodel v1.6.0 by ``em_extension`` URIs)

Edge Type Categories
~~~~~~~~~~~~~~~~~~~~

Temporal Relations
^^^^^^^^^^^^^^^^^^

**is_before**
   Chronological sequence (A before B). Not a type of its own: it is the
   **declared reverse** of ``is_after``, and since September 2026
   ``allowed_edges`` returns the reverse of every non-symmetric edge. A reverse
   is the same property read backwards, so it carries no mapping of its own.
   
   - See: ``is_after`` below
   - Source: StratigraphicNode
   - Target: StratigraphicNode

**is_after**
   Chronological sequence (A after B)
   
   - CIDOC-CRM: ``crmarchaeo:AP28_occurs_before``
   - CRMarchaeo: ``AP28_occurs_after``

**has_same_time**
   Contemporaneous elements
   
   - CIDOC-CRM: ``crmarchaeo:AP22_is_equal_in_time_to``
   - CRMarchaeo: ``AP22_is_equal_in_time_to``

**changed_from**
   Temporal transformation (one unit becoming another)
   
   - CIDOC-CRM: ``P123i_resulted_from``
   - Extension: ``AP4_produced_surface (was_surface_produced_by)``
   - CRMarchaeo: ``AP4_produced_surface``

Physical Relations
^^^^^^^^^^^^^^^^^^

**abuts**
   Physical contact relationship
   
   - CIDOC-CRM: *none holds — declared absent, see* :doc:`crmem`
   - Extension: ``AP11_has_physical_relation_to``
   - CRMarchaeo: ``AP11_has_physical_relation``

**fills**
   One unit filling another
   
   - CRMarchaeo: ``AP11_has_physical_relation``

**cuts / is_cut_by**
   Cutting relationships
   
   - CRMarchaeo: ``AP11_has_physical_relation``

**covers / is_covered_by**
   Covering relationships
   
   - CRMarchaeo: ``AP11_has_physical_relation``

**bonded_to** (older spelling: ``is_bonded_to``)
   Structural bonding. Symmetric: no reverse.

   - CRMarchaeo: ``AP11_has_physical_relation_to``, projected as ``em:bondedTo``

**equals** (older spelling: ``is_physically_equal_to``)
   Two unit ids for the same physical entity. Symmetric: no reverse.

   - CRMarchaeo: ``AP11_has_physical_relation_to``, projected as
     ``em:physicallyEquals``

**Older spellings** (``spelling_of``, connections datamodel 1.6.20)
   An entry carrying ``spelling_of: <canonical>`` is the SAME relation under
   an older name: the same RDF projection, **accepted when read, never
   written**. ``connections_loader`` reports it with ``is_canonical: False``
   and ``canonical_name`` set, ``normalize_edge_name`` returns the canonical,
   and ``spellings(name)`` lists every accepted name — readers ask that
   instead of keeping their own list, writers write the canonical. It is not
   ``deprecated``: a deprecated edge is dropped from RDF, and pyArchInit data
   still carries these names. See ``docs/SOURCE_OF_TRUTH.md``.

**leans_against**
   Leaning relationship
   
   - CRMarchaeo: ``AP11_has_physical_relation``

**rests_on**
   Resting/support relationship
   
   - CRMarchaeo: ``AP11_has_physical_relation``

Documentation Relations
^^^^^^^^^^^^^^^^^^^^^^^

**has_documentation**
   Links stratigraphic unit to documentation
   
   - CIDOC-CRM: ``P70i_is_documented_in``
   - Source: StratigraphicNode, SpecialFindUnit
   - Target: DocumentNode

**extracted_from**
   Information extracted from source
   
   - CIDOC-CRM: ``P67_refers_to``
   - Extension: ``J7_is_based_on_evidence_from (is_evidence_for)``
   - CRMinf: ``J7_is_based_on_evidence_from``
   - Source: ExtractorNode
   - Target: DocumentNode

**combines**
   Combining information from sources
   
   - CIDOC-CRM: ``P16_used_specific_object``
   - Extension: ``J1_used_as_premise (was_premise_for)``
   - CRMinf: ``J1_used_as_premise``
   - Source: CombinerNode
   - Target: ExtractorNode

Property Relations
^^^^^^^^^^^^^^^^^^

**has_property**
   Associates property with node
   
   - CIDOC-CRM: ``P43_has_dimension``
   - CRMem: ``em:hasQualia``
   - CRMarchaeo: ``AP9_took_matter_from``
   - Source: StratigraphicNode
   - Target: PropertyNode

Paradata Relations
^^^^^^^^^^^^^^^^^^

**is_in_paradata_nodegroup**
   Node belongs to paradata group
   
   - CIDOC-CRM: ``P106i_forms_part_of``
   - Source: DocumentNode, ExtractorNode, CombinerNode
   - Target: ParadataNodeGroup

**has_paradata_nodegroup**
   Node has associated paradata group
   
   - CIDOC-CRM: ``P129i_is_subject_of``
   - Source: StratigraphicNode
   - Target: ParadataNodeGroup

Group Relations
^^^^^^^^^^^^^^^

**is_in_activity**
   Part of archaeological activity
   
   - CIDOC-CRM: *none holds — declared absent, see* :doc:`crmem`
   - CRMem: ``em:isInActivity``
   - Source: Various node types
   - Target: ActivityNodeGroup

**is_in_timebranch / has_timebranch**
   Alternative temporal sequences
   
   - CIDOC-CRM: ``P67_refers_to``
   - CRMem: ``em:belongsToAlternative``
   - Source: StratigraphicNode
   - Target: TimeBranchNodeGroup

.. sync: manual

**contrasts_with**
   Mutually exclusive time branches. Symmetric, so it has no reverse. Renamed
   from ``incompatible_with``.
   
   - CIDOC-CRM: *none holds — declared absent.* ``P15_was_influenced_by`` has
     ``E7_Activity`` as its domain while a time branch is an ``E4_Period``, and
     it states influence rather than mutual exclusion
   - CRMem: ``em:contrastsWith``
   - Source/Target: TimeBranchNodeGroup

Epoch Relations
^^^^^^^^^^^^^^^

**has_first_epoch**
   Initial appearance epoch
   
   - CIDOC-CRM: ``P10_falls_within``
   - CRMem: ``em:firstAttestedInEpoch``
   - CRMarchaeo: ``AP13_has_stratigraphic_relation``
   - Source: StratigraphicNode, RepresentationModelNode
   - Target: EpochNode

**survive_in_epoch**
   Continues to exist in epoch
   
   - CIDOC-CRM: ``P132_spatiotemporally_overlaps_with``
   - CRMem: ``em:survivesInEpoch``
   - CRMarchaeo: ``AP13_has_stratigraphic_relation``

Representation Relations
^^^^^^^^^^^^^^^^^^^^^^^^

**has_representation_model**
   3D model of stratigraphic unit
   
   - CIDOC-CRM: ``P138i_has_representation``
   - Source: StratigraphicNode, EpochNode
   - Target: RepresentationModelNode

**has_representation_model_doc**
   3D model of documentation
   
   - Source: ExtractorNode, DocumentNode, CombinerNode
   - Target: RepresentationModelDocNode

**has_representation_model_sf**
   3D model of special find
   
   - Source: SpecialFindUnit
   - Target: RepresentationModelSpecialFindNode

**has_semantic_shape**
   Symbolic shape representation
   
   - CIDOC-CRM: ``P138i_has_representation``
   - CRMem: ``em:hasSemanticShape``
   - Source: Any Node
   - Target: SemanticShapeNode

Reference Relations
^^^^^^^^^^^^^^^^^^^

**has_geoposition**
   Geographic position
   
   - CIDOC-CRM: ``P53_has_former_or_current_location``
   - CRMgeo: ``Q4_has_spatial_projection``
   - Source: StratigraphicNode, ParadataNode
   - Target: GeoPositionNode

**has_linked_resource**
   External resource link
   
   - CIDOC-CRM: ``P67_refers_to``
   - Extension: ``L19_stores (is_stored_on)``
   - CRMdig: ``L19_stores``
   - Source: Various nodes
   - Target: LinkNode

**has_author**
   Author/creator
   
   - CIDOC-CRM: ``prov:wasAttributedTo``
   - CRMem: ``em:hasAuthor``
   - CRMdig: ``L10_had_input``
   - Source: Most node types
   - Target: AuthorNode

**has_license**
   Licensing information
   
   - CIDOC-CRM: ``P104_is_subject_to``
   - Source: Node, GraphNode
   - Target: LicenseNode

**has_embargo**
   Temporal embargo
   
   - CIDOC-CRM: ``P104_is_subject_to``
   - Source: LicenseNode
   - Target: EmbargoNode

Generic Relations
^^^^^^^^^^^^^^^^^

**generic_connection**
   Non-specific connection
   
   - CIDOC-CRM: ``P130_shows_features_of``
   - Extension: ``AP11_has_physical_relation_to (is_physical_relation_from)``
   - CRMarchaeo: ``AP11_has_physical_relation``
   - Source/Target: Any Node

Containment Relations
^^^^^^^^^^^^^^^^^^^^^

**is_part_of**
   Physical containment: child is part of container. A redeposited find inside a
   layer is written this way; the layer stays a US, because containment is a
   relation and not a node type.

   - CIDOC-CRM: ``P46i_forms_part_of``
   - Extension: ``AP21i_is_contained_in`` (CRMarchaeo), emitted only when the
     container is a ``StratigraphicUnit`` — the one class that maps to
     ``A2 Stratigraphic Volume Unit``, which is ``AP21i``'s range. Until
     2026-09-25 this slot held ``P46_is_composed_of``, the inverse of the core
     predicate, which the exporter emitted with the same subject and object.
   - Source: SpecialFindUnit, VirtualSpecialFindUnit, ReusedSpecialFind,
     StratigraphicUnit, DocumentaryStratigraphicUnit, VirtualStratigraphicUnit,
     FunctionalUnitNodeGroup
   - Target: StratigraphicUnit, DocumentaryStratigraphicUnit, VirtualSpecialFindUnit

**has_part**
   Declared reverse of ``is_part_of``. A reverse carries no mapping of its own:
   ``is_part_of`` emits ``P46i_forms_part_of`` — with ``AP21i_is_contained_in``
   beside it when the container is a US — and reading it backwards is the same
   property, not a second one.

   - See: ``is_part_of`` above

Visual Reference Relations
^^^^^^^^^^^^^^^^^^^^^^^^^^

**has_visual_reference**
   Links a node to a visual reference (added in v1.5.4)

   - CIDOC-CRM: ``P138i_has_representation``
   - CRMem: ``em:hasVisualReference``
   - Source: Various node types
   - Target: DocumentNode

Edge Definition Structure
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "is_before": {
           "name": "is_before",
           "label": "Chronological Sequence",
           "description": "One item occurs before another",
           "mapping": {
               "cidoc": "P120_occurs_before",
               "cidoc_extension": "CIDOC-CRM",
               "extension_mapping": "AP28_occurs_before",
               "extension_name": "CRMarchaeo"
           },
           "allowed_connections": {
               "source": ["StratigraphicNode"],
               "target": ["StratigraphicNode"]
           }
       }
   }

Visual Rules
------------

File: ``em_visual_rules.json``

This file defines visual representation rules for nodes in Blender (EM-tools).

Structure
~~~~~~~~~

.. code-block:: json

   {
       "visual_rules_version": "1.5.0",
       "default_settings": {
           "default_scale": 1.0,
           "default_color": [0.8, 0.8, 0.8, 1.0]
       },
       "node_visuals": {
           "US": {
               "3d_file": "src/3D/stratigraphic_unit.glb",
               "2d_file_rast": "src/2D/us.png",
               "2d_file_vect": "src/2D/us.svg",
               "style": {
                   "material": {
                       "rgba_color": {
                           "r": 0.5,
                           "g": 0.5,
                           "b": 0.5,
                           "a": 1.0
                       }
                   },
                   "border_color": "#000000",
                   "fill_color": "#FFFFFF",
                   "border_style": "solid",
                   "shape": "rectangle"
               },
               "label_position": "bottom"
           }
       }
   }

Visual Properties
~~~~~~~~~~~~~~~~~

For each node type:

- **3d_file**: Path to 3D proxy model (glTF/GLB)
- **2d_file_rast**: Raster icon (PNG)
- **2d_file_vect**: Vector icon (SVG)
- **style**: Visual styling
  
  - **material**: RGBA color for 3D material
  - **border_color**: Border color (hex)
  - **fill_color**: Fill color (hex)
  - **border_style**: solid, dashed, dotted
  - **shape**: rectangle, ellipse, pentagon, etc.

- **label_position**: bottom, over, side

Loading Configuration Files
----------------------------

Configuration files are loaded automatically when s3dgraphy is imported:

.. code-block:: python

   # From s3dgraphy/graph.py
   import json
   import os
   
   # Load connection rules
   rules_path = os.path.join(
       os.path.dirname(__file__), 
       "./JSON_config/em_connection_rules.json"
   )
   with open(rules_path) as f:
       connection_rules = json.load(f)["rules"]
       print('s3Dgraphy rules are correctly loaded.')

Accessing Configuration Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from s3dgraphy import Graph
   
   # Connection rules are available in Graph class
   graph = Graph("my_graph")
   
   # Rules are validated when adding edges
   graph.add_edge("edge_1", "US001", "US002", "is_before")
   # This checks allowed_connections from JSON config

Custom Configuration
--------------------

You can extend the configuration files for custom node or edge types:

Adding Custom Node Type
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "CustomArchaeologicalUnit": {
           "class": "CustomArchaeologicalUnit",
           "parent": "StratigraphicNode",
           "abbreviation": "CAU",
           "label": "Custom Archaeological Unit",
           "description": "Custom unit type for specific project needs",
           "s3Dgraphy_file": "custom_node.py",
           "mapping": {
               "cidoc": "E18 Physical Thing",
               "cidoc_s3d": "CustomUnit",
               "alternative": null
           },
           "properties": {
               "name": "P1_is_identified_by",
               "description": "P3_has_note",
               "custom_property": "P2_has_type"
           }
       }
   }

Adding Custom Edge Type
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: json

   {
       "custom_relationship": {
           "name": "custom_relationship",
           "label": "Custom Relationship",
           "description": "Project-specific relationship type",
           "mapping": {
               "cidoc": "P130_shows_features_of",
               "cidoc_extension": "CIDOC-CRM",
               "extension_mapping": null,
               "extension_name": null
           },
           "allowed_connections": {
               "source": ["StratigraphicNode"],
               "target": ["StratigraphicNode"]
           }
       }
   }

Configuration Validation
------------------------

s3dgraphy validates configuration at runtime:

.. code-block:: python

   # Invalid edge type raises error
   try:
       graph.add_edge("e1", "US001", "DOC001", "invalid_type")
   except ValueError as e:
       print(f"Error: {e}")
       # Error: Edge type 'invalid_type' not defined in configuration

   # Invalid connection raises error
   try:
       # PropertyNode -> StratigraphicNode not allowed
       graph.add_edge("e2", "PROP001", "US001", "has_property")
   except ValueError as e:
       print(f"Error: {e}")
       # Error: Connection not allowed by configuration

See Also
--------

- :doc:`s3dgraphy_import_export` - Import and export guide
- :doc:`api/s3dgraphy_classes_reference` - Complete API reference
- :doc:`s3dgraphy_integration_emtools` - EM-tools integration
