.. _edge-dtc_happened_on_device:

dtc_happened_on_device
======================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The APPARATUS a DTC step happened on — the camera, the scanner, the drone, the workstation.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Happened on device
   * - Label (it)
     - Avvenuto sul dispositivo
   * - Reverse
     - ``dtc_was_device_of``
   * - Source
     - :ref:`DTCNode <type-DTCNode>`
   * - Target
     - :ref:`DTCDeviceNode <type-DTCDeviceNode>`
   * - CIDOC
     - ``crmdig:L12_happened_on_device``

Description
-----------

The APPARATUS a DTC step happened on — the camera, the scanner, the drone, the workstation. CONTEXT, NOT CHAIN: it deliberately carries no \`dtc\_role\`, so a provenance walk does not traverse it (see \_dtc\_role\_note: an edge without dtc\_role is context by construction). A device is not a ring of the chain: it has no inputs and no outputs, and a walk that entered one would leave the flow to describe a thing.

From em
-------

.. code-block:: python

   em.graph.edges(type='dtc_happened_on_device')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'dtc_happened_on_device', target)    # the contract checks the pair

