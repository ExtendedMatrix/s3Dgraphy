.. _edge-dtc_derived_from:

dtc_derived_from
================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*DTC chain: the produced RESOURCE (ResourceNode) was derived from an acquisition (DTCInput) — the direct provenance shortcut alongside the process.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - DTC output derived from input
   * - Label (it)
     - L'uscita DTC deriva dall'ingresso
   * - Reverse
     - ``dtc_derivation_source_for``
   * - Source
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`ResourceFileNode <type-ResourceFileNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`ResourceFileNode <type-ResourceFileNode>`
   * - CIDOC
     - ``crmdig:L21_used_as_derivation_source · prov:wasDerivedFrom``

Description
-----------

DTC chain: the produced RESOURCE (ResourceNode) was derived from an acquisition (DTCInput) — the direct provenance shortcut alongside the process. ECHOES DTC substrate profile. Dual projection CRMdig + PROV-O.

From em
-------

.. code-block:: python

   em.graph.edges(type='dtc_derived_from')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'dtc_derived_from', target)    # the contract checks the pair

