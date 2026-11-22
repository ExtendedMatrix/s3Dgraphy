.. _type-DTCProcessNode:

DTCProcessNode
==============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.60) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A DTC PROCESS step: the transformation/processing event that turns inputs into produced digital objects (data.dtc\_kind from the \`process\` axis, e.g.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DTCProcessNode``
   * - node_type
     - ``dtc_process``
   * - Parent
     - :ref:`DTCNode <type-DTCNode>`
   * - Label (en)
     - DTC Process
   * - Label (it)
     - Processo DTC
   * - CIDOC
     - ``crmdig:D7_Digital_Machine_Event``

Description
-----------

A DTC PROCESS step: the transformation/processing event that turns inputs into produced digital objects (data.dtc\_kind from the \`process\` axis, e.g. transformation). Projected as a crmdig:D7\_Digital\_Machine\_Event / prov:Activity; its inputs and outputs are the dtc\_had\_input (prov:used) and dtc\_had\_output (prov:generated) edges.

*Italiano*: Un passo di PROCESSO DTC: l'evento di trasformazione/elaborazione che converte gli ingressi in oggetti digitali prodotti (data.dtc\_kind dall'asse \`process\`, ad es. transformation). Proiettato come crmdig:D7\_Digital\_Machine\_Event / prov:Activity; i suoi ingressi e le sue uscite sono gli archi dtc\_had\_input (prov:used) e dtc\_had\_output (prov:generated).

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``dtc_kind``
     - P2\_has\_type
   * - ``technique``
     - em:technique
   * - ``parameters``
     - em:parameters
   * - ``software``
     - em:software

Edges
-----

**Outgoing** (this node is the source): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`dtc_had_output <edge-dtc_had_output>`, :ref:`dtc_happened_on_device <edge-dtc_happened_on_device>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='dtc_process'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a dtc_process") as tx:        # create: one step of undo
       nid = tx.add_node('dtc_process', "name", description="…")

