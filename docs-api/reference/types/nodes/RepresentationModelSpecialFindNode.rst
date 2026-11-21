.. _type-RepresentationModelSpecialFindNode:

RepresentationModelSpecialFindNode
==================================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*3D representation of a Special Find — e.g.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``RepresentationModelSpecialFindNode``
   * - node_type
     - ``representation_model_sf``
   * - Parent
     - :ref:`RepresentationNode <type-RepresentationNode>`
   * - Label (en)
     - Representation Model Special Find
   * - Label (it)
     - Modello di rappresentazione di reperto
   * - CIDOC
     - ``D1 Digital Object``

Description
-----------

3D representation of a Special Find — e.g. a scanned capital repositioned according to an anastylosis hypothesis. Linked via crm:P138\_represents to a SpecialFindUnit / VirtualSpecialFind. Specialization of em:RepresentationModel.

*Italiano*: Rappresentazione 3D di un Reperto speciale — ad es. un capitello scansionato e ricollocato secondo un'ipotesi di anastilosi. Collegata tramite crm:P138\_represents a uno SpecialFindUnit / VirtualSpecialFind. Specializzazione di em:RepresentationModel.

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
   * - ``transform``
     - position: em:position, rotation: em:rotationDegrees, rotation\_order: em:rotationOrder, scale: em:scale, up\_axis: em:upAxis, pivot: em:pivot

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_representation_model_group <edge-is_in_representation_model_group>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_digital_object_part <edge-has_digital_object_part>`, :ref:`has_representation_model_doc <edge-has_representation_model_doc>`, :ref:`has_representation_model_sf <edge-has_representation_model_sf>`, :ref:`is_on_resource <edge-is_on_resource>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='representation_model_sf'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a representation_model_sf") as tx:        # create: one step of undo
       nid = tx.add_node('representation_model_sf', "name", description="…")

