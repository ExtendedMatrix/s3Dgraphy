.. _type-DTCAcquisitionNode:

DTCAcquisitionNode
==================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A DTC ACQUISITION step: the digital event by which an asset ENTERS this study from an (opaque, Tier-0) external source — a data-transfer / ingestion event, DISTINCT from the genesis DTCProcessNode.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DTCAcquisitionNode``
   * - node_type
     - ``dtc_acquisition``
   * - Parent
     - :ref:`DTCNode <type-DTCNode>`
   * - Label (en)
     - DTC Acquisition
   * - Label (it)
     - Acquisizione DTC
   * - CIDOC
     - ``crmdig:D12_Data_Transfer_Event``

Description
-----------

A DTC ACQUISITION step: the digital event by which an asset ENTERS this study from an (opaque, Tier-0) external source — a data-transfer / ingestion event, DISTINCT from the genesis DTCProcessNode. Projected as crmdig:D12\_Data\_Transfer\_Event (a subclass of D7\_Digital\_Machine\_Event, ⊂ prov:Activity): 'events that transfer a digital object from one digital carrier to another; normally the digital object remains the same' — the object arrives opaque, no genesis is asserted. Tier 0: single-ring chain — the acquisition event --dtc\_had\_output[prov:generated]--> the acquired Resource (ResourceNode); the upstream root is an opaque external entity recorded as literals on data (repo/record/agent/retrieved\_at/rights), not a genesis sub-graph. data.dtc\_kind from the \`acquisition\` axis (two families since 1.6.22 — capture: photo / laserscanner / topographic / gnss\_survey / field\_drawing / recording\_sheet; retrieval: download / local\_import / uri\_reference / ingest). Keeps genesis != acquisition as distinct TYPES inside the one DTC substrate.

*Italiano*: Un passo di ACQUISIZIONE DTC: l'evento digitale con cui un asset ENTRA in questo studio da una fonte esterna (opaca, Tier-0) — un evento di trasferimento/ingestione di dati, DISTINTO dal DTCProcessNode di genesi. Proiettato come crmdig:D12\_Data\_Transfer\_Event (sottoclasse di D7\_Digital\_Machine\_Event, ⊂ prov:Activity): «eventi che trasferiscono un oggetto digitale da un supporto digitale a un altro; normalmente l'oggetto digitale resta lo stesso» — l'oggetto arriva opaco, nessuna genesi viene asserita. Tier 0: catena ad anello singolo — l'evento di acquisizione --dtc\_had\_output[prov:generated]--> la risorsa acquisita (ResourceNode); la radice a monte è un'entità esterna opaca registrata come letterali in data (repo/record/agent/retrieved\_at/rights), non un sottografo di genesi. data.dtc\_kind dall'asse \`acquisition\` (due famiglie dalla 1.6.22 — capture: photo / laserscanner / topographic / gnss\_survey / field\_drawing / recording\_sheet; retrieval: download / local\_import / uri\_reference / ingest). Mantiene genesi != acquisizione come TIPI distinti all'interno dell'unico substrato DTC.

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
   * - ``retrieved_from``
     - em:retrievedFrom

Edges
-----

**Outgoing** (this node is the source): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`dtc_had_output <edge-dtc_had_output>`, :ref:`dtc_happened_on_device <edge-dtc_happened_on_device>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`dtc_had_input <edge-dtc_had_input>`, :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='dtc_acquisition'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a dtc_acquisition") as tx:        # create: one step of undo
       nid = tx.add_node('dtc_acquisition', "name", description="…")

