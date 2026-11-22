.. _edge-bonded_to:

bonded_to
=========

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Canonical (v5.0 em\_data.xlsx) form of the bonding relation: this stratigraphic unit is physically bonded to the target.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Bonded to
   * - Label (it)
     - In legame con
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

Canonical (v5.0 em\_data.xlsx) form of the bonding relation: this stratigraphic unit is physically bonded to the target. Symmetric. Allowed between any two StratigraphicNode instances including USVs-USVs when two virtually-reconstructed elements are theoretically bonded (e.g. two missing blocks of the same inferred course).

From em
-------

.. code-block:: python

   em.graph.edges(type='bonded_to')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'bonded_to', target)    # the contract checks the pair

