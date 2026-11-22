.. _edge-cuts:

cuts
====

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*This stratigraphic unit cuts the target stratigraphic unit.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Cuts
   * - Label (it)
     - Taglia
   * - Reverse
     - ``is_cut_by``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - CIDOC
     - ``AP11_has_physical_relation_to``

Description
-----------

This stratigraphic unit cuts the target stratigraphic unit.

From em
-------

.. code-block:: python

   em.graph.edges(type='cuts')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'cuts', target)    # the contract checks the pair

