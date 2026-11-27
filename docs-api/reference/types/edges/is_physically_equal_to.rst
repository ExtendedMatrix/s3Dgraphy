.. _edge-is_physically_equal_to:

is_physically_equal_to
======================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Older spelling of 'equals' (see \`spelling\_of\`): two stratigraphic units are considered physically the same entity or continuous fabric.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is physically equal to
   * - Label (it)
     - È fisicamente uguale a
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

Older spelling of 'equals' (see \`spelling\_of\`): two stratigraphic units are considered physically the same entity or continuous fabric. Symmetric. Accepted when read, never written: every writer emits 'equals'.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_physically_equal_to')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_physically_equal_to', target)    # the contract checks the pair

