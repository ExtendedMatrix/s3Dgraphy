.. _edge-is_on_resource:

is_on_resource
==============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*The place a reading looked at (an AnnotationRegion) is ON something: a region2d on a specific image (or one page of a multi-page resource), a passage on a text document, a point/line/polyline on a 3D model.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is on resource
   * - Label (it)
     - Sta sulla risorsa
   * - Reverse
     - ``has_annotation_region``
   * - Source
     - :ref:`AnnotationRegionNode <type-AnnotationRegionNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`ResourceFileNode <type-ResourceFileNode>`
   * - CIDOC
     - ``P106i_forms_part_of · em:isOnResource``

Description
-----------

The place a reading looked at (an AnnotationRegion) is ON something: a region2d on a specific image (or one page of a multi-page resource), a passage on a text document, a point/line/polyline on a 3D model. Region -> ResourceNode/DocumentNode, and (since v1.6.27) -> RepresentationModelNode / RepresentationModelDocNode / RepresentationModelSpecialFindNode for the 3D kinds, and (since v1.6.54) -> ResourceFileNode: the one photograph of a set (a campaign) the region is on. The region also keeps the id in its own data.resource\_id, so it is readable alone; this edge is the graph's statement of it.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_on_resource')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_on_resource', target)    # the contract checks the pair

