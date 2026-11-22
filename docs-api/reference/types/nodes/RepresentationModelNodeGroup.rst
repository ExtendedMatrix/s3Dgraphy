.. _type-RepresentationModelNodeGroup:

RepresentationModelNodeGroup
============================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.57) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Typed aggregation of the representation models that form ONE named set published under a single Document — «Survey 2015» under D.01, «Reconstruction» under D.09 (EM16-RMNG, meeting of 2026-09-10).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``RepresentationModelNodeGroup``
   * - node_type
     - ``RepresentationModelNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - RM Container
   * - Label (it)
     - Contenitore RM
   * - CIDOC
     - ``E73 Information Object``

Description
-----------

Typed aggregation of the representation models that form ONE named set published under a single Document — «Survey 2015» under D.01, «Reconstruction» under D.09 (EM16-RMNG, meeting of 2026-09-10). Until then the RM container lived only as EM Tools' \`scene.rm\_containers\` PropertyGroup, so the grouping that gives the set its meaning was invisible to anyone reading the graph. IT SITS BESIDE, IT DOES NOT REPLACE: every member keeps its own epoch edges (has\_first\_epoch / survive\_in\_epoch) and the Document keeps its DIRECT has\_representation\_model edges to each model — the group is added on top and never put in between, so a consumer that ignores it reads exactly what it read before. Membership is the TAG axis 'is\_in\_representation\_model\_group', like is\_in\_functional\_unit and is\_in\_location, and m:n like them (E.D., 23 Oct 2026): a mesh can belong to several containers — a model of «Survey 2015» can also be in «Reconstruction, 2nd c. AD». The epochs stay on each model; the default epochs a container carries in EM Tools are a convenience of the scene that writes them on its models, never a statement of the group. A group may legally be EMPTY and may legally have NO Document: both are states the RM Manager UI already shows. NOT a FunctionalUnitNodeGroup (that aggregates stratigraphic units into a building component; these members are models, not units); NOT an ActivityNodeGroup (nothing happened here and the set has no formation event of its own); NOT the Document, which stays the documentary anchor — deleting the container removes the group and not the Document.

*Italiano*: Aggregazione tipizzata dei modelli di rappresentazione che formano UN insieme nominato pubblicato sotto un unico Documento — «Rilievo 2015» sotto D.01, «Ricostruzione» sotto D.09 (EM16-RMNG, riunione del 2026-09-10). Fino ad allora il contenitore RM esisteva solo come PropertyGroup \`scene.rm\_containers\` di EM Tools, per cui il raggruppamento che dà significato all'insieme era invisibile a chiunque leggesse il grafo. STA ACCANTO, NON SOSTITUISCE: ogni membro conserva i propri archi di epoca (has\_first\_epoch / survive\_in\_epoch) e il Documento conserva i propri archi DIRETTI has\_representation\_model verso ciascun modello — il gruppo si aggiunge sopra e non viene mai interposto, così un consumatore che lo ignora legge esattamente ciò che leggeva prima. L'appartenenza è l'asse di TAG 'is\_in\_representation\_model\_group', come is\_in\_functional\_unit e is\_in\_location, e come loro m:n (E.D., 23 ott 2026): una mesh può appartenere a più contenitori — un modello di «Rilievo 2015» può stare anche in «Ricostruzione, II sec. d.C.». Le epoche restano su ogni modello; le epoche di default che un contenitore porta in EM Tools sono una comodità della scena che le scrive sui suoi modelli, mai un'affermazione del gruppo. Un gruppo può legittimamente essere VUOTO e può legittimamente NON avere un Documento: entrambi sono stati che l'interfaccia di RM Manager già mostra. NON è un FunctionalUnitNodeGroup (che aggrega unità stratigrafiche in un componente edilizio; questi membri sono modelli, non unità); NON è un ActivityNodeGroup (qui non è accaduto nulla e l'insieme non ha un proprio evento di formazione); NON è il Documento, che resta l'ancora documentaria — eliminare il contenitore rimuove il gruppo e non il Documento.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``acquired``
     - date
   * - ``valid_until``
     - date
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``frame``
     - —
   * - ``active_alternative``
     - —

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_representation_model_group <edge-is_in_representation_model_group>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`is_in_representation_model_group <edge-is_in_representation_model_group>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='RepresentationModelNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a RepresentationModelNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('RepresentationModelNodeGroup', "name", description="…")

