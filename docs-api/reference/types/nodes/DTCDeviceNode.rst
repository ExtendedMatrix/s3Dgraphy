.. _type-DTCDeviceNode:

DTCDeviceNode
=============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The APPARATUS a DTC step happened on — camera, sensor, drone, computer, scanner, total station, GNSS receiver.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DTCDeviceNode``
   * - node_type
     - ``dtc_device``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - DTC Device
   * - Label (it)
     - Dispositivo DTC
   * - CIDOC
     - ``crmdig:D8_Digital_Device``

Description
-----------

The APPARATUS a DTC step happened on — camera, sensor, drone, computer, scanner, total station, GNSS receiver. Projected as crmdig:D8\_Digital\_Device and attached to the EVENT by dtc\_happened\_on\_device (crmdig:L12\_happened\_on\_device), never to the input or the output: the three dtc\_kinds flow axes are what went in, what happened and what came out, and a device is what it happened ON. Until 2026-09-16 it was a STRING inside how.acquisition, and a string cannot be asked «what did this machine produce» or «that lens was distorted, which models are affected». NOT a DTCNode: a DTC node is a STEP (an event in the chain) and a device is a thing in the world — it has no inputs, no outputs, and a provenance walk has no business entering it; subclassing would have put it in the chain by inheritance and set the class hierarchy arguing with dtc\_role. data.dtc\_kind comes from the \`device\` axis of dtc\_kinds (em\_visual\_rules.json), so adding an apparatus is a JSON entry plus a sign. THE ID IS DERIVED FROM THE DESCRIPTOR (make \| model \| serial) by uuid5 — the same mechanism bucket\_acquisition uses for a campaign name, but WITHOUT the graph\_id in the key, because a campaign is an event of one study while the same camera in two studies is one camera. WHAT THAT COSTS, DECLARED: without a serial number two identical bodies derive the same id and MERGE, and the graph then cannot say which body took a given file. data.distinguishes records which happened ('serial' = one body, 'make+model' = a model). A declared merge is better than an invented distinction: salting the id with a graph or a timestamp would make two records of the SAME camera look like two cameras, and that failure is silent. Gated out of the stratigrapher palette, like every DTC node.

*Italiano*: L'APPARECCHIO su cui è avvenuto un passo DTC — fotocamera, sensore, drone, computer, scanner, stazione totale, ricevitore GNSS. Proiettato come crmdig:D8\_Digital\_Device e collegato all'EVENTO tramite dtc\_happened\_on\_device (crmdig:L12\_happened\_on\_device), mai all'ingresso o all'uscita: i tre assi di flusso di dtc\_kinds sono ciò che è entrato, ciò che è accaduto e ciò che è uscito, e un dispositivo è ciò SU CUI è accaduto. Fino al 2026-09-16 era una STRINGA dentro how.acquisition, e a una stringa non si può chiedere «che cosa ha prodotto questa macchina» o «quell'obiettivo era distorto, quali modelli ne sono interessati». NON è un DTCNode: un nodo DTC è un PASSO (un evento della catena) e un dispositivo è una cosa del mondo — non ha ingressi né uscite, e un percorso di provenienza non ha motivo di entrarvi; renderlo sottoclasse lo avrebbe inserito nella catena per ereditarietà e avrebbe messo la gerarchia delle classi in contraddizione con dtc\_role. data.dtc\_kind proviene dall'asse \`device\` di dtc\_kinds (em\_visual\_rules.json), quindi aggiungere un apparecchio significa aggiungere una voce JSON e un segno. L'ID È DERIVATO DAL DESCRITTORE (make \| model \| serial) tramite uuid5 — lo stesso meccanismo che bucket\_acquisition usa per il nome di una campagna, ma SENZA il graph\_id nella chiave, perché una campagna è un evento di un solo studio mentre la stessa fotocamera in due studi è una sola fotocamera. IL COSTO, DICHIARATO: senza numero di serie due corpi macchina identici derivano lo stesso id e si FONDONO, e il grafo non può più dire quale corpo abbia prodotto un dato file. data.distinguishes registra quale dei due casi si è verificato ('serial' = un corpo macchina, 'make+model' = un modello). Una fusione dichiarata è meglio di una distinzione inventata: salare l'id con un grafo o una marca temporale farebbe sembrare due registrazioni della STESSA fotocamera due fotocamere diverse, e questo errore è silenzioso. Escluso dalla palette dello stratigrafo, come ogni nodo DTC.

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
   * - ``make``
     - P2\_has\_type
   * - ``model``
     - P2\_has\_type
   * - ``serial``
     - P1\_is\_identified\_by

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`dtc_happened_on_device <edge-dtc_happened_on_device>`, :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='dtc_device'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a dtc_device") as tx:        # create: one step of undo
       nid = tx.add_node('dtc_device', "name", description="…")

