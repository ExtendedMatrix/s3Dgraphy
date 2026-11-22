.. _type-CombinerNode:

CombinerNode
============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node that represents the act of combining MULTIPLE extracted beliefs into a single conclusion.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``CombinerNode``
   * - node_type
     - ``combiner``
   * - Parent
     - :ref:`ParadataNode <type-ParadataNode>`
   * - Label (en)
     - Combiner
   * - Label (it)
     - Combinatore
   * - CIDOC
     - ``crminf:I5_Inference_Making``

Description
-----------

Node that represents the act of combining MULTIPLE extracted beliefs into a single conclusion. The 'X and Y therefore Z' step in the EM paradata chain: combiner takes multiple ExtractorNode inputs and produces a synthesized assertion. Distinct from ExtractorNode (single-source belief adoption).

*Italiano*: Nodo che rappresenta l'atto di combinare PIÙ convinzioni estratte in un'unica conclusione. È il passaggio «X e Y, quindi Z» nella catena dei paradati di EM: il combinatore riceve più ExtractorNode in ingresso e produce un'asserzione di sintesi. Distinto da ExtractorNode (adozione di una convinzione da una singola fonte).

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
   * - ``landmark_pose``
     - —
   * - ``combiner``
     - —
   * - ``name``
     - P1\_is\_identified\_by
   * - ``description``
     - P3\_has\_note

Edges
-----

**Outgoing** (this node is the source): :ref:`combines <edge-combines>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_representation_model_doc <edge-has_representation_model_doc>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_data_provenance <edge-has_data_provenance>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='combiner'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a combiner") as tx:        # create: one step of undo
       nid = tx.add_node('combiner', "name", description="…")

