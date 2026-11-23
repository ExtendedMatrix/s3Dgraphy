.. _type-LandscapeSurfaceNode:

LandscapeSurfaceNode
====================

.. note::

   Generated from the datamodels (nodes 1.6.56, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The ground surface of a landscape: a DEM (a gis\_layer GeoTIFF of raster.kind dem) drawn as a mesh, and optionally an image (an orthophoto, raster.kind image) draped on it — the two layers reached by has\_linked\_resource, the site it is the ground of by is\_in\_location.*

.. list-table::
   :widths: 25 75

   * - Class
     - ``LandscapeSurfaceNode``
   * - node_type
     - ``landscape_surface``
   * - Parent
     - :ref:`Node <type-Node>`
   * - Label (en)
     - Landscape surface
   * - Label (it)
     - Superficie del paesaggio
   * - CIDOC
     - ``crmdig:D1_Digital_Object``

Description
-----------

The ground surface of a landscape: a DEM (a gis\_layer GeoTIFF of raster.kind dem) drawn as a mesh, and optionally an image (an orthophoto, raster.kind image) draped on it — the two layers reached by has\_linked\_resource, the site it is the ground of by is\_in\_location. A GEOMETRY of the place, not its identity (the LocationNodeGroup) and not a representation of a stratigraphic node (the RepresentationModelNode).

*Italiano*: La superficie del suolo di un paesaggio: un DEM (un gis\_layer GeoTIFF di raster.kind dem) disegnato come mesh e, se c'è, un'immagine (un'ortofoto, raster.kind image) drappeggiata sopra — i due layer raggiunti con has\_linked\_resource, il sito di cui è il suolo con is\_in\_location. Una GEOMETRIA del luogo, non la sua identità (il LocationNodeGroup) né la rappresentazione di un nodo stratigrafico (il RepresentationModelNode).

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
   * - ``step_m``
     - —
   * - ``vertical_exaggeration``
     - —

Edges
-----

**Outgoing** (this node is the source): :ref:`generic_connection <edge-generic_connection>`, :ref:`has_embargo <edge-has_embargo>`, :ref:`has_license <edge-has_license>`, :ref:`has_linked_resource <edge-has_linked_resource>`, :ref:`has_semantic_shape <edge-has_semantic_shape>`, :ref:`has_translation <edge-has_translation>`, :ref:`is_in_location <edge-is_in_location>`

**Incoming** (this node is the target): :ref:`generic_connection <edge-generic_connection>`

From em
-------

.. code-block:: python

   for n in em.graph.nodes(type='landscape_surface'):   # read
       print(n.id, n.name, n.description)

   with em.write("Add a landscape_surface") as tx:        # create: one step of undo
       nid = tx.add_node('landscape_surface', "name", description="…")

