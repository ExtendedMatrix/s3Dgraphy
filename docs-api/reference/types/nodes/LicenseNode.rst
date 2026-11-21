.. _type-LicenseNode:

LicenseNode
===========

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents the license under which a node (or the whole graph via GraphNode) is published.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``LicenseNode``
   * - node_type
     - ``license``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - License
   * - Label (it)
     - Licenza
   * - CIDOC
     - ``E30 Right``

Description
-----------

Represents the license under which a node (or the whole graph via GraphNode) is published. Identified by license\_type (e.g. 'CC-BY-4.0') and url to the license text. Connected via has\_license edge to Nodes or GraphNode.

*Italiano*: Rappresenta la licenza con cui è pubblicato un nodo (o l'intero grafo tramite GraphNode). Identificata da license\_type (ad es. 'CC-BY-4.0') e dall'url del testo della licenza. Collegata tramite l'arco has\_license a nodi o al GraphNode.

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
   * - ``license_type``
     - P2\_has\_type
   * - ``url``
     - P1\_is\_identified\_by

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_license <edge-has_license>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='license'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a license") as tx:        # create: one step of undo
       nid = tx.add_node('license', "name", description="…")

