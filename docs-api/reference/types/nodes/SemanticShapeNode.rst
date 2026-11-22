.. _type-SemanticShapeNode:

SemanticShapeNode
=================

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*3D proxy geometry (convex shapes or spheres) representing the spatial extent of a node.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``SemanticShapeNode``
   * - node_type
     - ``semantic_shape``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Semantic Shape
   * - Label (it)
     - Forma semantica
   * - CIDOC
     - ``E73 Information Object``

Description
-----------

3D proxy geometry (convex shapes or spheres) representing the spatial extent of a node. Used as a semantic proxy distinct from a full RepresentationModel: lighter weight, intended for spatial indexing and rough containment, not for visual rendering. Linked via crm:P138\_represents to any Node.

*Italiano*: Geometria proxy 3D (forme convesse o sfere) che rappresenta l'estensione spaziale di un nodo. Usata come proxy semantico distinto da un RepresentationModel completo: più leggera, destinata all'indicizzazione spaziale e al contenimento approssimativo, non alla resa visiva. Collegata tramite crm:P138\_represents a qualsiasi Node.

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
   * - ``type``
     - P2\_has\_type
   * - ``convexshapes``
     - em:convexShape
   * - ``spheres``
     - em:sphere
   * - ``transform``
     - position: em:position, rotation: em:rotationDegrees, rotation\_order: em:rotationOrder, scale: em:scale, up\_axis: em:upAxis, pivot: em:pivot

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='semantic_shape'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a semantic_shape") as tx:        # create: one step of undo
       nid = tx.add_node('semantic_shape', "name", description="…")

