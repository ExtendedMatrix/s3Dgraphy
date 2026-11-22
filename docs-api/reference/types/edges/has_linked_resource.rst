.. _edge-has_linked_resource:

has_linked_resource
===================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects a node to its linked resource(s).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has linked resource
   * - Label (it)
     - Ha collegamento
   * - Reverse
     - ``is_linked_resource_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`SemanticShapeNode <type-SemanticShapeNode>`, :ref:`AnnotationRegionNode <type-AnnotationRegionNode>`, :ref:`RepresentationModelNodeGroup <type-RepresentationModelNodeGroup>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`LandscapeSurfaceNode <type-LandscapeSurfaceNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`
   * - CIDOC
     - ``P67_refers_to · L19_stores (is_stored_on)``

Description
-----------

Connects a node to its linked resource(s). From a representation model or an RM container to a 3D resource, the edge is the HAT of the resource's asset (1.6.41): what the object represents is said once, on the master, and its versions inherit it.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_linked_resource')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_linked_resource', target)    # the contract checks the pair

