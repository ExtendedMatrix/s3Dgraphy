.. _edge-has_representation_model:

has_representation_model
========================

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects epochs with their representation models in 3D space.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has representation model
   * - Label (it)
     - Ha modello di rappresentazione
   * - Reverse
     - ``is_representation_model_of``
   * - Source
     - :ref:`EpochNode <type-EpochNode>`, :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`
   * - Target
     - :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelNodeGroup <type-RepresentationModelNodeGroup>`
   * - CIDOC
     - ``P138i_has_representation``

Description
-----------

Connects epochs with their representation models in 3D space.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_representation_model')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_representation_model', target)    # the contract checks the pair

