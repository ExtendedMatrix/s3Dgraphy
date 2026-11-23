.. _type-StudyNode:

StudyNode
=========

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*HC9 Study (HDT-O, ECHOES D7.1): a scholarly activity (research/analysis/documentation, any domain) about a Heritage Entity (HC1), with a disciplinary focus, that produces documentary outputs contributing to an HDT.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``StudyNode``
   * - node_type
     - ``study``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Study
   * - Label (it)
     - Studio
   * - CIDOC
     - ``hdto:HC9_Study``

Description
-----------

HC9 Study (HDT-O, ECHOES D7.1): a scholarly activity (research/analysis/documentation, any domain) about a Heritage Entity (HC1), with a disciplinary focus, that produces documentary outputs contributing to an HDT. In EM one study corresponds to one graph: the study is the investigation, the graph (HC16/em:EMGraph) its content, created through HP25 — the sense of «a graph is a study» (StratiGraph D3.1 §3.3, D3.2 §3.5). The two stay distinct classes. Chain: Project -includes(crm:P9)-> Study -was\_about(HP23)-> HeritageEntity ; Study -produced(HP25)-> GraphNode. HDT-O-view node: not shown in the stratigrapher palette.

*Italiano*: HC9 Study (HDT-O, ECHOES D7.1): un'attività scientifica (ricerca/analisi/documentazione, in qualsiasi ambito) su un'Entità patrimoniale (HC1), con un orientamento disciplinare, che produce esiti documentari che contribuiscono a un HDT. In EM uno studio corrisponde a un grafo: lo studio è l'indagine, il grafo (HC16/em:EMGraph) il suo contenuto, creato tramite HP25 — il senso di «un grafo è uno studio» (StratiGraph D3.1 §3.3, D3.2 §3.5). Le due classi restano distinte. Catena: Project -includes(crm:P9)-> Study -was\_about(HP23)-> HeritageEntity ; Study -produced(HP25)-> GraphNode. Nodo della vista HDT-O: non mostrato nella palette dello stratigrafo.

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

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`study_about_heritage <edge-study_about_heritage>`, :ref:`study_produced_proposition_set <edge-study_produced_proposition_set>`, :ref:`study_took_place_at <edge-study_took_place_at>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`includes_study <edge-includes_study>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='study'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a study") as tx:        # create: one step of undo
       nid = tx.add_node('study', "name", description="…")

