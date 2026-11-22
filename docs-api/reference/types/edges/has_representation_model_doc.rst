.. _edge-has_representation_model_doc:

has_representation_model_doc
============================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects extractors, combiners and documents node to their representation model in 3D space.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has document representation model
   * - Label (it)
     - Ha modello di rappresentazione di documento
   * - Reverse
     - ``is_doc_representation_model_of``
   * - Source
     - :ref:`ExtractorNode <type-ExtractorNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`CombinerNode <type-CombinerNode>`
   * - Target
     - :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`
   * - CIDOC
     - ``P138i_has_representation``

Description
-----------

Connects extractors, combiners and documents node to their representation model in 3D space.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_representation_model_doc')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_representation_model_doc', target)    # the contract checks the pair

