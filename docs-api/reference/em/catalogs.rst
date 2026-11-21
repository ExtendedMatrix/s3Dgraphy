``em.catalogs`` — the datamodel's catalogues
============================================

Generated for em API |api| from the docstrings of :mod:`s3dgraphy.em.catalogs`.

What of s3Dgraphy is where in ``em``:

.. list-table::
   :header-rows: 1
   :widths: 35 35 30

   * - s3Dgraphy
     - in ``em``
     - reference
   * - node types (68) and edge types (63)
     - ``em.graph`` (views), ``em.catalogs.node_types()`` / ``edge_types()``
     - :doc:`../types/index`
   * - qualia (property types), property names
     - ``em.catalogs.qualia_types()`` (core), ``em.profiles.qualia_types()`` (+ packages), ``em.catalogs.property_names()``
     - this page, :doc:`vocab`
   * - document types, extractor types, accuracy levels
     - ``em.catalogs.document_types()`` / ``extractor_types()`` / ``accuracy_levels()``; with the packages ``em.profiles.document_types()`` / ``extractor_types()``
     - this page, :doc:`vocab`
   * - visual rules, colour ramps, palette icons, state symbols
     - ``em.catalogs.visual_rules()`` / ``color_ramps()`` / ``palette_icons()`` / ``state_symbols()``
     - this page
   * - alternative cases, basemap sources, translations of the datamodel
     - ``em.catalogs.alternative_cases()`` / ``basemap_sources()`` / ``translations()``
     - this page
   * - epochs and groups of a document
     - nodes of the graph: ``em.graph.nodes(type="EpochNode")``, the groups' types; ``em.graph.chronology()``
     - :doc:`graph`, :doc:`../types/index`
   * - authorities and vocabularies
     - ``em.vocab`` (concept, search, installed)
     - :doc:`vocab`
   * - the DTC (data transformation chain)
     - its node types (``DTC*``) through ``em.graph``; ``em.stamp`` for a derived artifact
     - :doc:`../types/index`, :doc:`stamps`

.. automodule:: s3dgraphy.em.catalogs
   :members:
   :show-inheritance:
