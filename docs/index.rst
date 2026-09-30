s3dgraphy Documentation
========================

.. only:: html

   |version_badge|

   .. image:: https://img.shields.io/badge/python-3.9+-brightgreen.svg
      :target: https://python.org
      :alt: Python

   .. image:: https://img.shields.io/badge/license-GPL--3.0-orange.svg
      :target: https://github.com/ExtendedMatrix/s3Dgraphy/blob/main/LICENSE
      :alt: License

**s3dgraphy** is a Python library that implements the `Extended Matrix <https://www.extendedmatrix.org>`_ formal language
for archaeological stratigraphic documentation and virtual reconstruction processes.
It provides the core graph structure and node management system that powers the
Extended Matrix Framework (EMF).

.. note::

   **s3dgraphy and Extended Matrix are not the same thing.** Extended Matrix (EM) is a *formal visual language* -- a human-readable notation for stratigraphic sequences, designed to be authored and reviewed by archaeologists using graph editors or AI-assisted tools. s3dgraphy is its *computational counterpart*: the Python library that encodes EM knowledge as a property knowledge graph (GraphML/JSON) and enables software tools to read, write, validate, and exchange that knowledge. Think of EM as the score and s3dgraphy as the engine that plays it.

.. admonition:: Where this manual sits in the EM ecosystem
   :class: hint

   You are reading the **s3dgraphy** manual — the Python library that
   powers Extended Matrix. For the broader EM ecosystem (the formal
   language, EM Tools for Blender, 3DSC, Heriverse), see
   :ref:`em-ecosystem-map` at the bottom of this page.

What is s3dgraphy?
------------------

s3dgraphy is the **core graph library** for Extended Matrix, providing:

- **Graph data structures** for archaeological documentation
- **Node and edge types** specific to stratigraphy and paradata
- **Import capabilities** from GraphML, XLSX, and SQLite databases
- **Export to JSON** for web visualization platforms
- **Export to GraphML** for round-trip editing in yEd and other graph editors
- **Container group nodes** for mereological (part--whole) relationships
- **Instance chains** for tracking objects across epochs via ``changed_from`` edges
- **CIDOC-CRM mappings** for semantic interoperability
- **Integration with EM-tools** for Blender 3D visualization

Key Features
------------

**Graph-Based Architecture**
   Native support for complex archaeological relationships and temporal sequences

**Stratigraphic Modeling**
   Specialized node types for stratigraphic units, documentation, and interpretation:

   - Physical units (US, SF, USD) and their serial variants (serSU, serUSD)
   - Virtual reconstructions (USV/s, USV/n, serUSVn, VSF)
   - Transformation units (TSU)
   - Documentation (DOC)
   - Paradata chains (EXT, COMB, PROP)

**Container Group Nodes**
   Stratigraphic units (US, USD, VSF) can act as containers for other elements,
   expressing mereological (part--whole) relationships via ``is_part_of`` / ``has_part``
   edges. In yEd, containers are represented as group nodes with specific background
   colors (US: ``#9B3333``, USD: ``#D86400``, VSF: ``#B19F61``).

**Instance Chains**
   The ``changed_from`` connector links the same physical object across different
   epochs into a navigable chain. For example, a capital found on the ground today
   (SF), the same capital as a collapsed element in a previous epoch (USD), and the
   same capital in its original Roman-era position (US) form a single instance chain.

**Format Interoperability**
   Full round-trip import/export:

   - **GraphML** -- Primary format with UUID slipback for edit-import cycles
   - **GraphML export** -- Re-export graphs to GraphML preserving structure and containers
   - **XLSX** -- Excel files with JSON mapping configurations
   - **SQLite** -- pyArchInit database support
   - **JSON** -- Export for web platforms (Heriverse, ATON)

**UUID Slipback System**
   Automatic UUID persistence in GraphML files enables:

   - Edit graphs in yEd while preserving node/edge identity
   - Duplicate EMID detection and automatic resolution
   - Seamless roundtrip editing workflow

**Comment Node Skipping**
   yEd comment/note nodes (yellow fill colors ``#FFCC00``, ``#FFFF00``, ``#FFFF99``)
   are automatically detected and skipped during GraphML import, so annotations in
   the graph editor do not pollute the archaeological data.

**Archaeological Standards**
   Built-in support for CIDOC-CRM mapping with extensions:

   - CIDOC-CRM (core)
   - CRMarchaeo (archaeological)
   - CRMdig (digital provenance)
   - CRMgeo (geographic)
   - CRMinf (argumentation)
   - CRMem (Extended Matrix custom extension; formerly CIDOC-S3D — em: namespace in em.ttl)

**Performance Optimized**
   Graph indexing system for efficient queries on large datasets

**Blender Integration**
   Direct integration with EM-tools for 3D archaeological visualization

Quick Start
-----------

Installation
~~~~~~~~~~~~

Install s3dgraphy using pip:

.. code-block:: bash

   pip install s3dgraphy

Or from source:

.. code-block:: bash

   git clone https://github.com/ExtendedMatrix/s3Dgraphy.git
   cd s3dgraphy
   pip install -e .

Basic Usage
~~~~~~~~~~~

Create and populate a graph:

.. code-block:: python

   from s3dgraphy import Graph
   from s3dgraphy.nodes import StratigraphicNode, DocumentNode

   # Create a new graph
   graph = Graph("pompeii_house_vii")

   # Add a stratigraphic unit
   us001 = StratigraphicNode("US001", name="US001", description="Mosaic floor, main atrium")
   graph.add_node(us001)

   # Add documentation
   doc001 = DocumentNode("DOC001", name="DOC001", description="Floor photograph")
   graph.add_node(doc001)

   # Create relationship
   graph.add_edge("edge_001", "US001", "DOC001", "has_documentation")

   print(f"Graph contains {len(graph.nodes)} nodes and {len(graph.edges)} edges")

Import from GraphML
~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from s3dgraphy import GraphMLImporter

   # Import GraphML file (graph is created automatically)
   importer = GraphMLImporter("excavation_data.graphml")
   graph = importer.parse()

   print(f"Imported {len(graph.nodes)} nodes")

   # Check for warnings
   if graph.warnings:
       print("Import warnings:")
       for warning in graph.warnings:
           print(f"  - {warning}")

Export to GraphML
~~~~~~~~~~~~~~~~~

.. code-block:: python

   from s3dgraphy.exporter.graphml import GraphMLExporter

   # Export graph back to GraphML
   exporter = GraphMLExporter(graph)
   exporter.export("output/site_data.graphml")

Export to JSON
~~~~~~~~~~~~~~

.. code-block:: python

   from s3dgraphy.exporter.json_exporter import JSONExporter

   # Create exporter and export all graphs
   exporter = JSONExporter("output/project.json")
   exporter.export_graphs()

Import from XLSX
~~~~~~~~~~~~~~~~

.. code-block:: python

   from s3dgraphy.importer import MappedXLSXImporter
   from s3dgraphy import Graph

   # Create graph and import with predefined mapping
   graph = Graph("xlsx_import")
   importer = MappedXLSXImporter(
       filepath="stratigraphic_units.xlsx",
       mapping_name="emdb_basic",
       graph=graph
   )

   graph = importer.parse()
   print(f"Imported {len(graph.nodes)} nodes from XLSX")

Architecture Overview
---------------------

Core Components
~~~~~~~~~~~~~~~

**Graph Class**
   Central container managing nodes and edges with indexing for performance

**Node Types**
   Specialized classes for different archaeological entities:

   - StratigraphicNode (US, USV, SF, VSF, USD, TSU) and serial variants (serSU, serUSD, serUSVn)
   - ParadataNode (DOC, EXT, COMB, PROP)
   - GroupNode (Paradata groups, time branches, activities)
   - RepresentationModelNode (3D models for US, DOC, SF)
   - ReferenceNode (GEO, LINK, EP, AUTH)

**Edge Types**
   Defined relationships with CIDOC-CRM mappings:

   - Temporal (is_after, is_before, has_same_time, changed_from)
   - Containment (is_part_of, has_part)
   - Documentation (has_data_provenance, extracted_from, combines)
   - Properties (has_property)
   - Paradata (has_paradata_nodegroup, is_in_paradata_nodegroup)
   - Epochs (has_first_epoch, survive_in_epoch)
   - Representation (has_representation_model, has_semantic_shape)
   - Contrast (contrasts_with)

**Import System**
   Modular importers for GraphML, XLSX, SQLite with JSON mapping support

**Export System**
   GraphML exporter for round-trip editing; JSON exporter for web visualization

**Multi-Graph Manager**
   Manage multiple graphs within a single project

JSON Configuration Files
~~~~~~~~~~~~~~~~~~~~~~~~~

s3dgraphy uses three core JSON configuration files:

1. **s3Dgraphy_node_datamodel.json**

   - Defines all node types and properties
   - CIDOC-CRM mappings for each node type
   - Node hierarchy and inheritance

2. **s3Dgraphy_connections_datamodel.json**

   - Defines all edge types
   - CIDOC-CRM mappings for relationships
   - Allowed source/target node combinations

3. **em_visual_rules.json**

   - Visual representation rules for Blender
   - 3D models, 2D icons, colors, styles

See :doc:`s3dgraphy_json_config` for detailed documentation,
:doc:`ontology-mapping-system` for how these three files drive the RDF
projection, and :doc:`generated-report` for the version each of them currently
carries.

.. note::

   Datamodel version numbers are deliberately **not** written out on this page.
   They move independently of the library version and a hand-copied one goes
   stale in a week; :doc:`generated-report` reads them off the files at build
   time.

Use Cases
---------

Archaeological Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create comprehensive stratigraphic documentation:

.. code-block:: python

   from s3dgraphy import Graph
   from s3dgraphy.nodes import StratigraphicNode

   # Document stratigraphic sequence
   graph = Graph("excavation_area_a")

   # Add units
   wall = StratigraphicNode("US001", name="US001", description="Stone wall foundation")
   floor = StratigraphicNode("US002", name="US002", description="Mosaic floor")

   # Add temporal relationship (canonical direction: recent -> ancient)
   graph.add_node(wall)
   graph.add_node(floor)
   graph.add_edge("e1", "US002", "US001", "is_after")  # floor is after (more recent than) wall

Virtual Reconstruction
~~~~~~~~~~~~~~~~~~~~~~

Document 3D reconstruction processes:

.. code-block:: python

   from s3dgraphy.nodes import StratigraphicNode, DocumentNode, ExtractorNode

   # Virtual unit
   usv = StratigraphicNode("USV001", name="USV001", description="Reconstructed upper wall")

   # Link to documentation
   doc = DocumentNode("DOC001", name="DOC001", description="Archaeological parallels")

   # Extraction process
   ext = ExtractorNode("EXT001", name="EXT001")

   graph.add_node(usv)
   graph.add_node(doc)
   graph.add_node(ext)

   # Create paradata chain
   graph.add_edge("e1", "EXT001", "DOC001", "extracted_from")
   graph.add_edge("e2", "USV001", "EXT001", "has_paradata_nodegroup")

Data Integration
~~~~~~~~~~~~~~~~

Import from multiple sources:

.. code-block:: python

   from s3dgraphy import GraphMLImporter
   from s3dgraphy.importer import MappedXLSXImporter
   from s3dgraphy.exporter.json_exporter import JSONExporter

   # Import GraphML base structure
   importer1 = GraphMLImporter("base_stratigraphy.graphml")
   graph = importer1.parse()

   # Add data from Excel
   importer2 = MappedXLSXImporter(
       filepath="additional_data.xlsx",
       mapping_name="emdb_basic",
       graph=graph
   )
   graph = importer2.parse()

   # Export combined data
   exporter = JSONExporter("combined_data.json")
   exporter.export_graphs()

Extended Matrix Ecosystem
--------------------------

s3dgraphy is part of the broader Extended Matrix Framework:

**EM-tools for Blender**
   3D visualization and annotation using s3dgraphy as core library

**Extended Matrix Documentation**
   Formal language reference and tutorials

**3D Survey Collection (3DSC)**
   High-quality 3D model preparation

**ATON 3 Framework**
   Web-based archaeological visualization

**Heriverse Platform**
   Virtual heritage experiences and visualization

Repository and Resources
------------------------

**GitHub Repository**
   https://github.com/ExtendedMatrix/s3Dgraphy

**PyPI Package**
   https://pypi.org/project/s3dgraphy/

**EM-tools for Blender**
   https://github.com/zalmoxes-laran/EM-blender-tools

**Extended Matrix Project**
   https://www.extendedmatrix.org

**Issue Tracker**
   https://github.com/ExtendedMatrix/s3Dgraphy/issues

Community & Support
-------------------

**Telegram Group**
   https://t.me/UserGroupEM

**Facebook Group**
   https://www.facebook.com/groups/extendedmatrix

**Email Contact**
   emanuel.demetrescu@cnr.it

Current Status
--------------

**Version**: 1.6.0 (development series ``1.6.0.devN``)

**Datamodel**: see :doc:`generated-report` (derived at build time)

**Status**: Active development (Beta)

**Python**: 3.9+

**License**: GPL-3.0-or-later

Roadmap
-------

Completed Features
~~~~~~~~~~~~~~~~~~

- Core graph structure with indexing
- Node type system with CIDOC-CRM mappings
- GraphML import with UUID slipback
- GraphML export with container group support
- XLSX import with mapping system (per-table mappings + row filters)
- Unified single-file workbook (``em_data.xlsx``) import **and** export
- SQLite **and** PostgreSQL pyArchInit bridge (``s3dgraphy.sync``)
- JSON export for web platforms (Heriverse, ATON)
- RDF export (Turtle / N-Triples / JSON-LD / TriG) with CIDOC-CRM + HDT-O
- Temporal inference: TPQ/TAQ chronology closure with paradox detection
- Property propagation resolvers (node → swimlane → graph fallback)
- Graph merge with typed conflict resolution
- Container group nodes (US, USD, VSF as containers with is_part_of edges)
- Instance chains via changed_from edges
- Comment/note node skipping during import
- Multi-graph management
- Integration with EM-tools for Blender

Planned Features
~~~~~~~~~~~~~~~~

**Near-term** (next releases):

- Enhanced validation system
- Performance optimizations for very large graphs
- Additional CIDOC-CRM mapping refinements

**Long-term**:

- GeoJSON export for GIS integration
- Neo4j export for graph databases
- Command-line interface (CLI)
- Standalone GUI application

Table of Contents
=================

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   s3dgraphy_quickstart
   s3dgraphy_core_concepts

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   s3dgraphy_import_export
   s3dgraphy_mapping_system
   importers/mapping_schema
   importers/unified_xlsx_importer
   importers/dual_stack_driver_choice
   exporters/unified_xlsx_exporter
   s3dgraphy_json_config
   drawing-a-glyph
   s3dgraphy_integration_emtools

.. toctree::
   :maxdepth: 2
   :caption: Ontology alignment

   ontology-mapping-system
   crmem
   dtc-profile
   mapping-descriptors
   mapping-update-procedure
   hdto-coverage
   asset-dtc-protocol
   generated-report

.. toctree::
   :maxdepth: 2
   :caption: Quality and contribution

   data-quality
   development
   SOURCE_OF_TRUTH
   DATAMODEL_PROPAGATION

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/core
   api/nodes
   api/edges
   api/importers
   api/exporters
   api/sync
   api/classification
   api/resolvers
   api/diagnostics
   api/utils
   api/s3dgraphy_classes_reference
   api/s3dgraphy_edges_reference

.. toctree::
   :maxdepth: 2
   :caption: Internals & Design Notes

   internals/propagation
   internals/temporal
   internals/transforms
   internals/merge_patcher
   internals/classification
   internals/stratiminer_prompt
   DATA_FORMALIZATIONS
   GRAPHML_EXPORT

.. toctree::
   :maxdepth: 2
   :caption: Examples & Workflows

   tutorials/basic_usage
   examples/s3dgraphy_workflow_examples

.. toctree::
   :maxdepth: 2
   :caption: Development

   s3dgraphy_changelog
   s3dgraphy_roadmap
   deprecations

.. toctree::
   :maxdepth: 1
   :caption: Support

   s3dgraphy_troubleshooting

.. toctree::
   :maxdepth: 2
   :caption: Advanced

   guides/s3dgraphy_caching_performance
   guides/s3dgraphy_operators_guide

Citation
--------

If you use s3dgraphy in your research, please cite:

.. code-block:: bibtex

   @software{s3dgraphy,
     title = {s3dgraphy: Core Graph Library for Extended Matrix},
     author = {Demetrescu, Emanuel},
     year = {2026},
     url = {https://github.com/ExtendedMatrix/s3Dgraphy},
     version = {1.6.0}
   }

.. include:: _includes/em_ecosystem_map.rst

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
