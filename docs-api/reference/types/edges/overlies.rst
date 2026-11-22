.. _edge-overlies:

overlies
========

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*This stratigraphic unit overlies (covers) the target stratigraphic unit.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Overlies
   * - Label (it)
     - Copre
   * - Reverse
     - ``is_overlain_by``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - CIDOC
     - ``AP11_has_physical_relation_to``

Description
-----------

This stratigraphic unit overlies (covers) the target stratigraphic unit.

From em
-------

.. code-block:: python

   em.graph.edges(type='overlies')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'overlies', target)    # the contract checks the pair

