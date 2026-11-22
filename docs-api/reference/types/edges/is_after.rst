.. _edge-is_after:

is_after
========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates a temporal sequence where one item occurs after another.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is after
   * - Label (it)
     - È posteriore a
   * - Reverse
     - ``is_before``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - CIDOC
     - ``crmarchaeo:AP28_occurs_before``

Description
-----------

Indicates a temporal sequence where one item occurs after another. This is the canonical direction in Extended Matrix (from more recent to more ancient stratigraphic units).

From em
-------

.. code-block:: python

   em.graph.edges(type='is_after')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_after', target)    # the contract checks the pair

