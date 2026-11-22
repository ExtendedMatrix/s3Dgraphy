.. _edge-has_timebranch:

has_timebranch
==============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*[DEPRECATED in 1.6.0 — use is\_in\_timebranch] Indicates that a node is connected to a specific time branch.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has timebranch
   * - Label (it)
     - Ha il ramo temporale
   * - Reverse
     - ``is_timebranch_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
   * - CIDOC
     - ``P67_refers_to · em:belongsToAlternative``

Description
-----------

[DEPRECATED in 1.6.0 — use is\_in\_timebranch] Indicates that a node is connected to a specific time branch.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_timebranch')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_timebranch', target)    # the contract checks the pair

