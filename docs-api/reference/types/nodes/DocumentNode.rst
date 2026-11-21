.. _type-DocumentNode:

DocumentNode
============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Node that represents a document or source.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``DocumentNode``
   * - node_type
     - ``document``
   * - Parent
     - :ref:`ParadataNode <type-ParadataNode>`
   * - Label (en)
     - Document
   * - Label (it)
     - Documento
   * - CIDOC
     - ``E31 Document``

Description
-----------

Node that represents a document or source. Attributes: data (dict): Additional metadata, such as 'url\_type'.

*Italiano*: Nodo che rappresenta un documento o una fonte. Attributi: data (dict): metadati aggiuntivi, come 'url\_type'.

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
   * - ``catalog_stamp``
     - —
   * - ``name``
     - P102\_has\_title
   * - ``description``
     - P3\_has\_note

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_geoposition <edge-has_geoposition>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_property <edge-has_property>`, :ref:`has_representation_model <edge-has_representation_model>`, :ref:`has_representation_model_doc <edge-has_representation_model_doc>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_after <edge-is_after>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`, :ref:`survive_in_epoch <edge-survive_in_epoch>`

**Incoming** (this node is the target): :ref:`extracted_from <edge-extracted_from>`, :ref:`generic_connection <edge-generic_connection>`, :ref:`has_documentation <edge-has_documentation>`, :ref:`has_same_time <edge-has_same_time>`, :ref:`is_after <edge-is_after>`, :ref:`is_on_resource <edge-is_on_resource>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='document'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a document") as tx:        # create: one step of undo
       nid = tx.add_node('document', "name", description="…")

