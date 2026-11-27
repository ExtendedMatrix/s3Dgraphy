.. _edge-is_in_location:

is_in_location
==============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node belongs to a spatial / locational group (LocationNodeGroup).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in location
   * - Label (it)
     - È nel luogo
   * - Reverse
     - ``includes_location``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`CombinerNode <type-CombinerNode>`, :ref:`PropertyNode <type-PropertyNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`LandscapeSurfaceNode <type-LandscapeSurfaceNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`LocationNodeGroup <type-LocationNodeGroup>`
   * - CIDOC
     - ``P53_has_former_or_current_location``

Description
-----------

Indicates that a node belongs to a spatial / locational group (LocationNodeGroup). Membership is m:n (multiple is\_in\_location edges per source are allowed) and additive (memberships compose; none overrides). The optional 'is\_primary' attribute on at most one edge per source disambiguates which membership is rendered as a yEd group folder in em-graph. The same edge type also carries the recursive Location → Location hierarchy (Pompei → Sector 4 → Casa del Fauno → Room 12).

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_location')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_location', target)    # the contract checks the pair

