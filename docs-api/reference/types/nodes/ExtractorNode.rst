.. _type-ExtractorNode:

ExtractorNode
=============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.57) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node that represents the act of extracting information / adopting a belief FROM a single source (DocumentNode).*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ExtractorNode``
   * - node_type
     - ``extractor``
   * - Parent
     - :ref:`ParadataNode <type-ParadataNode>`
   * - Label (en)
     - Extractor
   * - Label (it)
     - Estrattore
   * - CIDOC
     - ``crminf:I7_Belief_Adoption``

Description
-----------

Node that represents the act of extracting information / adopting a belief FROM a single source (DocumentNode). The mediator between a source and an assertion: 'I adopted this belief because the source says so'. Distinct from CombinerNode which combines MULTIPLE extractions.

*Italiano*: Nodo che rappresenta l'atto di estrarre un'informazione / adottare una convinzione DA una singola fonte (DocumentNode). È il mediatore tra una fonte e un'asserzione: «ho adottato questa convinzione perché lo dice la fonte». Distinto da CombinerNode, che combina PIÙ estrazioni.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``act_start``
     - —
   * - ``act_end``
     - —
   * - ``em_kind``
     - —
   * - ``landmark``
     - —
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note
   * - ``url``
     - P1\_is\_identified\_by
   * - ``source``
     - J7\_is\_based\_on\_evidence\_from

Edges
-----

**Outgoing** (this node is the source): :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_representation_model_doc <edge-has_representation_model_doc>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`combines <edge-combines>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_data_provenance <edge-has_data_provenance>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='extractor'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a extractor") as tx:        # create: one step of undo
       nid = tx.add_node('extractor', "name", description="…")

