.. _edge-has_semantic_shape:

has_semantic_shape
==================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects any node to its semantic shape representation in 3D space.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has semantic shape
   * - Label (it)
     - Ha forma semantica
   * - Reverse
     - ``is_semantic_shape_of``
   * - Source
     - :ref:`Node <type-Node>`
   * - Target
     - :ref:`SemanticShapeNode <type-SemanticShapeNode>`
   * - CIDOC
     - ``P138i_has_representation · em:hasSemanticShape``

Description
-----------

Connects any node to its semantic shape representation in 3D space. Since v1.6.10 this is ALSO how a PropertyNode of type 'geometry' carries its payload: the proxy of a unit is a property, and the numbers (convex hulls / spheres, or a .glb via the shape's url) live in the SemanticShapeNode it points at. The source stays 'Node' — deliberately, and now for a reason worth writing down: narrowing it to the stratigraphic types would break the proxy-as-property model, which needs a PropertyNode to be a legal source.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_semantic_shape')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_semantic_shape', target)    # the contract checks the pair

