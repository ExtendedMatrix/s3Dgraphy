.. _edge-is_in_periodization:

is_in_periodization
===================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*An horizon belongs to a periodization (a set of horizons).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in periodization
   * - Label (it)
     - È nella periodizzazione
   * - Reverse
     - ``lists_horizon``
   * - Source
     - :ref:`HorizonNode <type-HorizonNode>`
   * - Target
     - :ref:`PeriodizationNode <type-PeriodizationNode>`
   * - CIDOC
     - ``P71_lists``

Description
-----------

An horizon belongs to a periodization (a set of horizons). Source the HorizonNode, target the PeriodizationNode. Both live in the container member graphs.periodizations, never in a study graph. New in 1.6.47 (MICRO-LAB orizzonti, E.D. 24 Oct 2026): no existing edge says it — is\_part\_of is physical containment, is\_in\_paradata\_nodegroup / is\_in\_activity / is\_in\_location gather nodes of a study by reasoning, intention or place, and has\_sub\_epoch is between epochs; a periodization is an AUTHORITY DOCUMENT that lists its spans, which CIDOC says with P71 lists.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_periodization')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_periodization', target)    # the contract checks the pair

