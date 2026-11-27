.. _type-ParadataNodeGroup:

ParadataNodeGroup
=================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Group node for paradata.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``ParadataNodeGroup``
   * - node_type
     - ``ParadataNodeGroup``
   * - Parent
     - :ref:`GroupNode <type-GroupNode>`
   * - Label (en)
     - Paradata Node Group
   * - Label (it)
     - Gruppo di paradati
   * - CIDOC
     - ``E89 Propositional Object``

Description
-----------

Group node for paradata. This group brings together all paradata related to a stratigraphic unit: typically named '[US\_name]\_PD' (ParaData).

*Italiano*: Nodo di gruppo per i paradati. Questo gruppo riunisce tutti i paradati relativi a un'unità stratigrafica: tipicamente denominato '[US\_name]\_PD' (ParaData).

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

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_author <edge-has_author>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_first_epoch <edge-has_first_epoch>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_activity <edge-is_in_activity>`, :ref:`is_in_location <edge-is_in_location>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_paradata_nodegroup <edge-has_paradata_nodegroup>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='ParadataNodeGroup'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a ParadataNodeGroup") as tx:        # create: one step of undo
       nid = tx.add_node('ParadataNodeGroup', "name", description="…")

