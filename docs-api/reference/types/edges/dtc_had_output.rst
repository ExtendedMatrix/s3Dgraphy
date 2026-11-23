.. _edge-dtc_had_output:

dtc_had_output
==============

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*DTC chain: a processing step (DTCProcess) produced a RESOURCE (a file: mesh/orthophoto/table…) — the ResourceNode (E73/D1), which is the SHARED HINGE that a RepresentationModel and/or a Document may reference.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - DTC process had output
   * - Label (it)
     - Il processo DTC ha avuto in uscita
   * - Reverse
     - ``dtc_was_output_of``
   * - Source
     - :ref:`DTCNode <type-DTCNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`
   * - CIDOC
     - ``crmdig:L11_had_output · prov:generated``

Description
-----------

DTC chain: a processing step (DTCProcess) produced a RESOURCE (a file: mesh/orthophoto/table…) — the ResourceNode (E73/D1), which is the SHARED HINGE that a RepresentationModel and/or a Document may reference. The produced ResourceNode carries data.dtc\_kind + resource\_type. ECHOES DTC substrate profile. Dual projection CRMdig + PROV-O.

From em
-------

.. code-block:: python

   em.graph.edges(type='dtc_had_output')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'dtc_had_output', target)    # the contract checks the pair

