.. _edge-equals:

equals
======

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Canonical (v5.0 em\_data.xlsx) form of the 'same physical entity' relation: two distinct unit IDs (from different campaigns or archival sources) refer to the same stratigraphic fact.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Equals
   * - Label (it)
     - Uguale a
   * - Reverse
     - —
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - CIDOC
     - ``AP11_has_physical_relation_to``

Description
-----------

Canonical (v5.0 em\_data.xlsx) form of the 'same physical entity' relation: two distinct unit IDs (from different campaigns or archival sources) refer to the same stratigraphic fact. Symmetric.

From em
-------

.. code-block:: python

   em.graph.edges(type='equals')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'equals', target)    # the contract checks the pair

