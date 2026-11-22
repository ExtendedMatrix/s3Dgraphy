.. _type-GraphNode:

GraphNode
=========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents the EM graph itself as a node, used as anchor for graph-wide metadata (author, license, embargo, default epoch, project-level provenance).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``GraphNode``
   * - node_type
     - ``graph``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Graph
   * - Label (it)
     - Grafo
   * - CIDOC
     - ``E73 Information Object``

Description
-----------

Represents the EM graph itself as a node, used as anchor for graph-wide metadata (author, license, embargo, default epoch, project-level provenance). Enables graph-level inheritance for metadata propagation: values declared on the GraphNode become defaults for all contained nodes unless overridden. Targeted by has\_author, has\_license, has\_embargo edges to carry global defaults. In HDT-O terms (D7.1) an EM graph is a Heritage Proposition Set (HC16) — a named graph carrying formal assertions about a heritage entity — and it corresponds one to one to the study that created it (StudyNode, HC9, through study\_produced\_proposition\_set / HP25). «A graph is a study» (StratiGraph D3.1 §3.3, D3.2 §3.5) names that correspondence; the two classes stay distinct, an activity and its content. The graph is not the digital twin: an HDTNode (HC2) gathers all the digital information about an asset at any scale. Connectable via contains\_proposition\_set (HP33) to one or more HDTNode (HC2 Heritage Digital Twin) instances.

*Italiano*: Rappresenta il grafo EM stesso come nodo, usato come ancora per i metadati a livello di grafo (autore, licenza, embargo, epoca predefinita, provenienza a livello di progetto). Consente l'ereditarietà a livello di grafo per la propagazione dei metadati: i valori dichiarati sul GraphNode diventano valori predefiniti per tutti i nodi contenuti, salvo ridefinizione. È destinazione degli archi has\_author, has\_license, has\_embargo che portano i valori predefiniti globali. In termini HDT-O (D7.1) un grafo EM è un Heritage Proposition Set (HC16) — un grafo nominato che porta asserzioni formali su un'entità patrimoniale — e corrisponde uno a uno allo studio che lo ha creato (StudyNode, HC9, tramite study\_produced\_proposition\_set / HP25). «Un grafo è uno studio» (StratiGraph D3.1 §3.3, D3.2 §3.5) nomina questa corrispondenza; le due classi restano distinte, un'attività e il suo contenuto. Il grafo non è il gemello digitale: un HDTNode (HC2) raccoglie tutte le informazioni digitali su un bene, a qualunque scala. Collegabile tramite contains\_proposition\_set (HP33) a una o più istanze di HDTNode (HC2 Heritage Digital Twin).

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

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`has_property <edge-has_property>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`contains_proposition_set <edge-contains_proposition_set>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`study_produced_proposition_set <edge-study_produced_proposition_set>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='graph'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a graph") as tx:        # create: one step of undo
       nid = tx.add_node('graph', "name", description="…")

