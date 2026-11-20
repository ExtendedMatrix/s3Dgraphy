.. _type-FunctionalUnitNodeGroup:

FunctionalUnitNodeGroup
=======================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Typed aggregation of the stratigraphic units that make up one recognisable functional/architectural component — the column made of its US, the wall made of its US (DP-72).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``FunctionalUnitNodeGroup``
   * - node_type
     - ``FunctionalUnitNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - Functional Unit
   * - Label (it)
     - Unità funzionale
   * - CIDOC
     - ``E24 Physical Human-Made Thing``

Description
-----------

Typed aggregation of the stratigraphic units that make up one recognisable functional/architectural component — the column made of its US, the wall made of its US (DP-72). Answers what a set of units IS, as a building component. Built BOTTOM-UP from the stratigraphic reading: the member units stay intact and fully stratigraphic underneath, each keeping its own epochs, paradata and provenance. Membership is a TAG axis, 'is\_in\_functional\_unit' (m:n, additive), NOT the nesting axis 'is\_part\_of': the relation is the same mereological P46i, but a Functional Unit legitimately SPANS EPOCHS (a wall built across four of them still carries the roof as one body) and a swimlane box cannot, so the functional reading lives in its own view beside pure stratigraphy without either constraining the other. NOT an ActivityNodeGroup (DP-43: a cluster of actions/processes — what was DONE, not what the units ARE); NOT a generic container (DP-36: a US/USD/VSF acting as container is still a stratigraphic unit with its own formation event, while a Functional Unit has none of its own); NOT a LocationNodeGroup of kind 'functional' (a named PLACE answering 'where', not a COMPONENT answering 'what'); NOT a geometric construction grammar (the geometry type travels BY REFERENCE via 'geometry\_type\_ref', nothing internalized). Attach rules: members StratigraphicNode --is\_in\_functional\_unit--> FunctionalUnit; nesting FunctionalUnit --is\_in\_functional\_unit--> FunctionalUnit (the capital inside the column); FunctionalUnit --is\_part\_of--> US stays legal and means the whole component PHYSICALLY EMBEDDED in a stratigraphic unit (a column engaged in a later wall). The orthogonal axes stay orthogonal: a member keeps its own has\_first\_epoch / is\_in\_activity / is\_in\_location, and the Functional Unit has NO epoch of its own — its temporal extent is DERIVED from its members and may cover several epochs. EM manual: 'SU / USD / VSF as Container' (Stratigraphic Nodes) and the is\_part\_of connector.

*Italiano*: Aggregazione tipizzata delle unità stratigrafiche che compongono un elemento funzionale/architettonico riconoscibile — la colonna fatta delle sue US, il muro fatto delle sue US (DP-72). Risponde a che cosa È un insieme di unità, in quanto componente edilizio. Costruita DAL BASSO a partire dalla lettura stratigrafica: le unità membro restano intatte e pienamente stratigrafiche al di sotto, ciascuna con le proprie epoche, i propri paradati e la propria provenienza. L'appartenenza è un asse di TAG, 'is\_in\_functional\_unit' (m:n, additivo), NON l'asse di annidamento 'is\_part\_of': la relazione è la stessa P46i mereologica, ma un'Unità funzionale ATTRAVERSA legittimamente PIÙ EPOCHE (un muro costruito nel corso di quattro di esse sostiene comunque il tetto come un unico corpo) mentre un riquadro di swimlane non può farlo, per cui la lettura funzionale vive in una propria vista accanto alla stratigrafia pura senza che l'una vincoli l'altra. NON è un ActivityNodeGroup (DP-43: un insieme di azioni/processi — ciò che è stato FATTO, non ciò che le unità SONO); NON è un contenitore generico (DP-36: una US/USD/VSF che funge da contenitore resta un'unità stratigrafica con un proprio evento di formazione, mentre un'Unità funzionale non ne ha uno proprio); NON è un LocationNodeGroup di tipo 'functional' (un LUOGO nominato che risponde a 'dove', non un COMPONENTE che risponde a 'che cosa'); NON è una grammatica costruttiva geometrica (il tipo di geometria viaggia PER RIFERIMENTO tramite 'geometry\_type\_ref', nulla viene internalizzato). Regole di collegamento: membri StratigraphicNode --is\_in\_functional\_unit--> FunctionalUnit; annidamento FunctionalUnit --is\_in\_functional\_unit--> FunctionalUnit (il capitello dentro la colonna); FunctionalUnit --is\_part\_of--> US resta lecito e significa che l'intero componente è FISICAMENTE INGLOBATO in un'unità stratigrafica (una colonna inglobata in un muro successivo). Gli assi ortogonali restano ortogonali: un membro conserva i propri has\_first\_epoch / is\_in\_activity / is\_in\_location, e l'Unità funzionale NON ha un'epoca propria — la sua estensione temporale è DERIVATA dai suoi membri e può coprire più epoche. Manuale EM: 'SU / USD / VSF as Container' (Stratigraphic Nodes) e il connettore is\_part\_of.

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
   * - ``geometry_type_ref``
     - Opaque pointer into an EXTERNAL geometry-type taxonomy (bSDD / Getty AAT / an HBIM shape-grammar vocabulary).

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='FunctionalUnitNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a FunctionalUnitNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('FunctionalUnitNodeGroup', "name", description="…")

