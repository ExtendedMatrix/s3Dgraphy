.. _edge-has_visual_reference:

has_visual_reference
====================

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that the element has an associated visual reference.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has visual reference
   * - Label (it)
     - Ha riferimento visivo
   * - Reverse
     - ``is_visual_reference_of``
   * - Source
     - :ref:`PropertyNode <type-PropertyNode>`
   * - Target
     - :ref:`ResourceNode <type-ResourceNode>`, :ref:`AnnotationRegionNode <type-AnnotationRegionNode>`
   * - CIDOC
     - ``P138i_has_representation · em:hasVisualReference``

Description
-----------

Indicates that the element has an associated visual reference.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_visual_reference')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_visual_reference', target)    # the contract checks the pair

