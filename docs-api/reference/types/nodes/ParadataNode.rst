.. _type-ParadataNode:

ParadataNode
============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Base class for nodes representing the reasoning chain (paradata) supporting an assertion.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ParadataNode``
   * - node_type
     - ``ParadataNode``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - ParadataNode
   * - Label (it)
     - —
   * - CIDOC
     - ``crminf:I1_Argumentation``

Description
-----------

Base class for nodes representing the reasoning chain (paradata) supporting an assertion. Not a document — the documentation lives at the source end of the chain (DocumentNode reached via ExtractorNode → CombinerNode → Paradata).

*Italiano*: Classe base per i nodi che rappresentano la catena di ragionamento (paradati) a sostegno di un'asserzione. Non è un documento — la documentazione risiede all'estremità della catena che corrisponde alla fonte (DocumentNode raggiunto tramite ExtractorNode → CombinerNode → Paradata).

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
   * - ``url``
     - P1\_is\_identified\_by

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='ParadataNode'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a ParadataNode") as tx:        # create: one step of undo
       nid = tx.add_node('ParadataNode', "name", description="…")

