.. _edge-extracted_from:

extracted_from
==============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that information is derived from a particular source: a source DOCUMENT, (since v1.6.10) an ANNOTATION REGION — the traced part of an image that a reading is based on — or (since v1.6.24) a STRATIGRAPHIC UNIT that itself has the property the extractor feeds.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Extracted from
   * - Label (it)
     - Estratto da
   * - Reverse
     - ``is_source_for_extraction``
   * - Source
     - :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`TranslationNode <type-TranslationNode>`
   * - Target
     - :ref:`DocumentNode <type-DocumentNode>`, :ref:`AnnotationRegionNode <type-AnnotationRegionNode>`, :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`PropertyNode <type-PropertyNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - CIDOC
     - ``P67_refers_to · J7_is_based_on_evidence_from (is_evidence_for)``

Description
-----------

Indicates that information is derived from a particular source: a source DOCUMENT, (since v1.6.10) an ANNOTATION REGION — the traced part of an image that a reading is based on — or (since v1.6.24) a STRATIGRAPHIC UNIT that itself has the property the extractor feeds.

From em
-------

.. code-block:: python

   em.graph.edges(type='extracted_from')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'extracted_from', target)    # the contract checks the pair

