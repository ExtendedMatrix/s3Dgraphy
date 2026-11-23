.. _edge-has_same_time:

has_same_time
=============

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that two elements are contemporaneous.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has same time
   * - Label (it)
     - Contemporaneo a
   * - Reverse
     - —
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - CIDOC
     - ``crmarchaeo:AP22_is_equal_in_time_to``

Description
-----------

Indicates that two elements are contemporaneous. This is a symmetric relation.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_same_time')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_same_time', target)    # the contract checks the pair

