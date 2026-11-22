.. _edge-is_in_timebranch:

is_in_timebranch
================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node belongs to a specific time branch.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in timebranch
   * - Label (it)
     - È nel ramo temporale
   * - Reverse
     - ``contains_in_timebranch``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
   * - CIDOC
     - ``P67_refers_to · em:belongsToAlternative``

Description
-----------

Indicates that a node belongs to a specific time branch.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_timebranch')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_timebranch', target)    # the contract checks the pair

