.. _edge-is_bonded_to:

is_bonded_to
============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Older spelling of 'bonded\_to' (see \`spelling\_of\`): this stratigraphic unit is physically bonded to the target stratigraphic unit (e.g., masonry bonding).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is bonded to
   * - Label (it)
     - Si lega a
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

Older spelling of 'bonded\_to' (see \`spelling\_of\`): this stratigraphic unit is physically bonded to the target stratigraphic unit (e.g., masonry bonding). Symmetric. Accepted when read, never written: every writer emits 'bonded\_to'.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_bonded_to')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_bonded_to', target)    # the contract checks the pair

