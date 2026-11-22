.. _edge-fills:

fills
=====

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*This stratigraphic unit fills the target stratigraphic unit (e.g., a deposit filling a cut).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Fills
   * - Label (it)
     - Riempie
   * - Reverse
     - ``is_filled_by``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - CIDOC
     - ``AP11_has_physical_relation_to``

Description
-----------

This stratigraphic unit fills the target stratigraphic unit (e.g., a deposit filling a cut).

From em
-------

.. code-block:: python

   em.graph.edges(type='fills')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'fills', target)    # the contract checks the pair

