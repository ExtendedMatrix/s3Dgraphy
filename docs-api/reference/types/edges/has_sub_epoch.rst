.. _edge-has_sub_epoch:

has_sub_epoch
=============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.62) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Splits an epoch into ordered sub-epochs (phases).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has sub-epoch
   * - Label (it)
     - Ha come sotto-epoca
   * - Reverse
     - ``is_in_epoch``
   * - Source
     - :ref:`EpochNode <type-EpochNode>`
   * - Target
     - :ref:`EpochNode <type-EpochNode>`
   * - CIDOC
     - ``P10_falls_within · em:hasSubEpoch``

Description
-----------

Splits an epoch into ordered sub-epochs (phases). Source is the parent epoch, target a phase (itself an EpochNode). Phases partition the parent's time-span; when hidden the parent epoch holds all the units, when shown the units are distributed across the phases. Reverse: is\_in\_epoch. 1.6.47 (MICRO-LAB orizzonti): the CHRONOLOGY reads it — the sub-epoch RESTRICTS the interval of its parent: its effective interval is the intersection of its own start/end with the parent's (a missing bound is the parent's; a bound outside the parent is brought back to it, with a warning), recursively. Graph.epoch\_intervals() gives it, and a unit dated by its epoch reports rule «sub\_epoch», source the parent epoch, relation has\_sub\_epoch when the bound came from the parent.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_sub_epoch')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_sub_epoch', target)    # the contract checks the pair

