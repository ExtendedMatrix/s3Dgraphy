.. _type-FunctionalUnitNodeGroup:

FunctionalUnitNodeGroup
=======================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

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

Typed aggregation of the stratigraphic units that make up one recognisable functional/architectural component — the column made of its US, the wall made of its US (DP-72). Answers what a set of units IS, as a building component. Built BOTTOM-UP from the stratigraphic reading: the member units stay intact and fully stratigraphic underneath, each keeping its own epochs, paradata and provenance. Membership is a TAG axis, 'is\_in\_functional\_unit' (m:n, additive), NOT the nesting axis 'is\_part\_of': the relation is the same mereological P46i, but a Functional Unit legitimately SPANS EPOCHS (a wall built across four of them still carries the roof as one body) and a swimlane box cannot, so the functional reading lives in its own view beside pure stratigraphy without either constraining the other. NOT an ActivityNodeGroup (DP-43: a cluster of actions/processes — what was DONE, not what the units ARE); NOT a generic container (DP-36: a US/USD/VSF acting as container is still a stratigraphic unit with its own formation event, while a Functional Unit has none of its own); NOT a LocationNodeGroup of kind 'functional' (a named PLACE answering 'where', not a COMPONENT answering 'what'); NOT a geometric construction grammar (the geometry type travels BY REFERENCE via 'geometry\_type\_ref', nothing internalized). Attach rules: members StratigraphicNode --is\_in\_functional\_unit--> FunctionalUnit; nesting FunctionalUnit --is\_in\_functional\_unit--> FunctionalUnit (the capital inside the column); FunctionalUnit --is\_part\_of--> US stays legal and means the whole component PHYSICALLY EMBEDDED in a stratigraphic unit (a column engaged in a later wall). The orthogonal axes stay orthogonal: a member keeps its own has\_first\_epoch / is\_in\_activity / is\_in\_location. AN IDENTITY IN TIME (1.6.52, MICRO-LG2, E.D. 20–21 Nov 2026): at every scale — from the column to the room, the building, the complex and the territory (scale) — a Functional Unit is an identity (the villa, the castle, the temple, the ruin, the restored temple) whose LIFE IS DECLARED, not derived from the members: has\_first\_epoch / survive\_in\_epoch and absolute dates (absolute\_time\_start / \_end) with their paradata. The members may be OLDER than the unit (the Roman wall reused in the castle is a member of the castle from the epoch of the castle): a member must be ALIVE in the life of the unit, which s3dgraphy.functional\_units checks, never derives. Its FUNCTION is the quale primary\_function (has\_property, with extractor → document), its USE a dated property of the same unit (property name use, data.valid\_from / data.valid\_to): a change of use without stratigraphic actions adds a property, not a node. When ANOTHER identity takes its place in the same volume (villa → castle, temple → ruin → restored temple) a new Functional Unit is born, changed\_from the former with change\_type transformation (E81, connections 1.6.56); PHASES with different US under the same function (wooden gate → stone gate) stay one unit. The highest unit of a site (none contains it) is the HANDLE of the site in the landscape (is\_in\_location the site); its slice on an horizon, the PRESENCE (crm:E93), is computed and never saved. A unit may live without members (the villa supposed from the roof tiles of a UT, its primary\_function extracted from the UT): its evidence is then a symbol. EM manual: 'SU / USD / VSF as Container' (Stratigraphic Nodes) and the is\_part\_of connector.

*Italiano*: Aggregazione tipizzata delle unità stratigrafiche che compongono un elemento funzionale/architettonico riconoscibile — la colonna fatta delle sue US, il muro fatto delle sue US (DP-72). Risponde a che cosa È un insieme di unità, in quanto componente edilizio. Costruita DAL BASSO a partire dalla lettura stratigrafica: le unità membro restano intatte e pienamente stratigrafiche al di sotto, ciascuna con le proprie epoche, i propri paradati e la propria provenienza. L'appartenenza è un asse di TAG, 'is\_in\_functional\_unit' (m:n, additivo), NON l'asse di annidamento 'is\_part\_of': la relazione è la stessa P46i mereologica, ma un'Unità funzionale ATTRAVERSA legittimamente PIÙ EPOCHE (un muro costruito nel corso di quattro di esse sostiene comunque il tetto come un unico corpo) mentre un riquadro di swimlane non può farlo, per cui la lettura funzionale vive in una propria vista accanto alla stratigrafia pura senza che l'una vincoli l'altra. NON è un ActivityNodeGroup (DP-43: un insieme di azioni/processi — ciò che è stato FATTO, non ciò che le unità SONO); NON è un contenitore generico (DP-36: una US/USD/VSF che funge da contenitore resta un'unità stratigrafica con un proprio evento di formazione, mentre un'Unità funzionale non ne ha uno proprio); NON è un LocationNodeGroup di tipo 'functional' (un LUOGO nominato che risponde a 'dove', non un COMPONENTE che risponde a 'che cosa'); NON è una grammatica costruttiva geometrica (il tipo di geometria viaggia PER RIFERIMENTO tramite 'geometry\_type\_ref', nulla viene internalizzato). Regole di collegamento: membri StratigraphicNode --is\_in\_functional\_unit--> FunctionalUnit; annidamento FunctionalUnit --is\_in\_functional\_unit--> FunctionalUnit (il capitello dentro la colonna); FunctionalUnit --is\_part\_of--> US resta lecito e significa che l'intero componente è FISICAMENTE INGLOBATO in un'unità stratigrafica (una colonna inglobata in un muro successivo). Gli assi ortogonali restano ortogonali: un membro conserva i propri has\_first\_epoch / is\_in\_activity / is\_in\_location. UN'IDENTITÀ NEL TEMPO (1.6.52, MICRO-LG2, E.D. 20–21 nov 2026): a ogni scala — dalla colonna all'ambiente, all'edificio, al complesso e al territorio (scale) — un'Unità funzionale è un'identità (la villa, il castello, il tempio, il rudere, il tempio restaurato) la cui VITA È DICHIARATA, non derivata dai membri: has\_first\_epoch / survive\_in\_epoch e date assolute (absolute\_time\_start / \_end) con i loro paradati. I membri possono essere PIÙ ANTICHI dell'unità (il muro romano riusato nel castello è membro del castello dall'epoca del castello): un membro deve essere VIVO nella vita dell'unità, cosa che s3dgraphy.functional\_units controlla, non deriva. La sua FUNZIONE è la qualia primary\_function (has\_property, con estrattore → documento), il suo USO una proprietà datata della stessa unità (nome di proprietà use, data.valid\_from / data.valid\_to): un cambio d'uso senza azioni stratigrafiche aggiunge una proprietà, non un nodo. Quando UN'ALTRA identità ne prende il posto nello stesso volume (villa → castello, tempio → rudere → tempio restaurato) nasce una nuova Unità funzionale, changed\_from la precedente con change\_type transformation (E81, connessioni 1.6.56); le FASI con US diverse sotto la stessa funzione (porta di legno → porta di pietra) restano una sola unità. L'unità più alta di un sito (nessuna la contiene) è la MANIGLIA del sito nel paesaggio (is\_in\_location il sito); la sua fetta su un orizzonte, la PRESENZA (crm:E93), si calcola e non si salva mai. Un'unità può vivere senza membri (la villa supposta dai coppi di una UT, con la primary\_function estratta dalla UT): la sua evidenza è allora un simbolo. Manuale EM: 'SU / USD / VSF as Container' (Stratigraphic Nodes) e il connettore is\_part\_of.

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
   * - ``scale``
     - 1.6.52 (MICRO-LG2, D-LG10): the SCALE of the functional unit — mereological, not a level of detail (the LOD belongs to the representation) nor a degree of evidence.

Edges
-----

**Outgoing** (this node is the source): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_property <edge-has_property>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_part_of <edge-is_part_of>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`changed_from <edge-changed_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_functional_unit <edge-is_in_functional_unit>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='FunctionalUnitNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a FunctionalUnitNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('FunctionalUnitNodeGroup', "name", description="…")

