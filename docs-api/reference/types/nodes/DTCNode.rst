.. _type-DTCNode:

DTCNode
=======

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Abstract base for one STEP of a DTC chain.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DTCNode``
   * - node_type
     - — (abstract: no node has it)
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - DTCNode
   * - Label (it)
     - —
   * - CIDOC
     - —

Description
-----------

Abstract base for one STEP of a DTC chain. Concrete subclasses set \`\`node\_type\`\`

Edges
-----

**Outgoing** (this node is the source): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`dtc_had_output <edge-dtc_had_output>`, :ref:`dtc_happened_on_device <edge-dtc_happened_on_device>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`generic_connection <edge-generic_connection>`

