.. _type-GeoPositionNode:

GeoPositionNode
===============

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Class to represent a GeoPosition node in the graph.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``GeoPositionNode``
   * - node_type
     - ``geo_position``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Geo Position
   * - Label (it)
     - Posizione geografica
   * - CIDOC
     - ``E53 Place``

Description
-----------

Class to represent a GeoPosition node in the graph. Attributes: type (str): Node type, set to 'geo\_position'. data (dict): Data related to geographic position.

*Italiano*: Classe che rappresenta un nodo GeoPosition nel grafo. Attributi: type (str): tipo di nodo, impostato a 'geo\_position'. data (dict): dati relativi alla posizione geografica.

Fields
------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Field
     - Mapping / note
   * - ``name``
     - P1\_is\_identified\_by
   * - ``epsg``
     - P168\_place\_is\_defined\_by
   * - ``shift_x``
     - Q9\_is\_expressed\_in\_terms\_of
   * - ``shift_y``
     - Q9\_is\_expressed\_in\_terms\_of
   * - ``shift_z``
     - Q9\_is\_expressed\_in\_terms\_of
   * - ``rotation``
     - Q9\_is\_expressed\_in\_terms\_of
   * - ``rotation_reference``
     - —
   * - ``datum_operation``
     - —

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_paradata_nodegroup <edge-is_in_paradata_nodegroup>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_geoposition <edge-has_geoposition>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='geo_position'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a geo_position") as tx:        # create: one step of undo
       nid = tx.add_node('geo_position', "name", description="…")

