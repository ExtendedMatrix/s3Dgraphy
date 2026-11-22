.. _edge-dtc_had_input:

dtc_had_input
=============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*DTC chain: a processing step (DTCProcess) consumed an input RESOURCE — a raw acquisition (photo/laser scan/…) = the ResourceNode (E73/D1).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - DTC process had input
   * - Label (it)
     - Il processo DTC ha avuto in ingresso
   * - Reverse
     - ``dtc_was_input_of``
   * - Source
     - :ref:`DTCNode <type-DTCNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`DTCNode <type-DTCNode>`
   * - CIDOC
     - ``crmdig:L10_had_input · prov:used``

Description
-----------

DTC chain: a processing step (DTCProcess) consumed an input RESOURCE — a raw acquisition (photo/laser scan/…) = the ResourceNode (E73/D1). ECHOES DTC substrate profile. Dual projection CRMdig + PROV-O.

From em
-------

.. code-block:: python

   em.graph.edges(type='dtc_had_input')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'dtc_had_input', target)    # the contract checks the pair

