.. _type-HeritageEntityNode:

HeritageEntityNode
==================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*HC1 Heritage Entity (HDT-O, ECHOES D7.1): the real-world entity socially recognized as having cultural/historical/scientific value that an HC2 Heritage Digital Twin (HDTNode) is a digital twin of.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``HeritageEntityNode``
   * - node_type
     - ``heritage_entity``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Heritage Entity
   * - Label (it)
     - Entità patrimoniale
   * - CIDOC
     - ``hdto:HC1_Heritage_Entity``

Description
-----------

HC1 Heritage Entity (HDT-O, ECHOES D7.1): the real-world entity socially recognized as having cultural/historical/scientific value that an HC2 Heritage Digital Twin (HDTNode) is a digital twin of. Completes the canonical HDT-O chain HC1 -has\_digital\_twin(HP1)-> HC2 -contains\_proposition\_set(HP33)-> HC16 (em:EMGraph/GraphNode). HDT-O-view node: not shown in the stratigrapher palette (like HDTNode/GraphNode). HC3 Tangible / HC4 Intangible specializations are deferred.

*Italiano*: HC1 Heritage Entity (HDT-O, ECHOES D7.1): l'entità del mondo reale socialmente riconosciuta come dotata di valore culturale/storico/scientifico, di cui un HC2 Heritage Digital Twin (HDTNode) è il gemello digitale. Completa la catena canonica HDT-O HC1 -has\_digital\_twin(HP1)-> HC2 -contains\_proposition\_set(HP33)-> HC16 (em:EMGraph/GraphNode). Nodo della vista HDT-O: non mostrato nella palette dello stratigrafo (come HDTNode/GraphNode). Le specializzazioni HC3 Tangible / HC4 Intangible sono rinviate.

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

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_twin <edge-has_digital_twin>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`heritage_part_of <edge-heritage_part_of>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`heritage_part_of <edge-heritage_part_of>`, :ref:`study_about_heritage <edge-study_about_heritage>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='heritage_entity'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a heritage_entity") as tx:        # create: one step of undo
       nid = tx.add_node('heritage_entity', "name", description="…")

