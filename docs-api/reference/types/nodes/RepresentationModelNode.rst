.. _type-RepresentationModelNode:

RepresentationModelNode
=======================

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*3D representation (model or spatialized image) of a stratigraphic node — real or virtual.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``RepresentationModelNode``
   * - node_type
     - ``representation_model``
   * - Parent
     - :ref:`RepresentationNode <type-RepresentationNode>`
   * - Label (en)
     - Representation Model
   * - Label (it)
     - Modello di rappresentazione
   * - CIDOC
     - ``D1 Digital Object``

Description
-----------

3D representation (model or spatialized image) of a stratigraphic node — real or virtual. Always linked to the represented node via crm:P138\_represents.

*Italiano*: Rappresentazione 3D (modello o immagine spazializzata) di un nodo stratigrafico — reale o virtuale. Sempre collegata al nodo rappresentato tramite crm:P138\_represents.

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
   * - ``url``
     - P1\_is\_identified\_by
   * - ``type``
     - P2\_has\_type
   * - ``frame``
     - —
   * - ``transform``
     - position: em:position, rotation: em:rotationDegrees, rotation\_order: em:rotationOrder, scale: em:scale, up\_axis: em:upAxis, pivot: em:pivot

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_representation_model_group <edge-is_in_representation_model_group>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_object_part <edge-has_digital_object_part>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`is_on_resource <edge-is_on_resource>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='representation_model'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a representation_model") as tx:        # create: one step of undo
       nid = tx.add_node('representation_model', "name", description="…")

