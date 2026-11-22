.. _edge-has_representation_model_sf:

has_representation_model_sf
===========================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects special find units to their representation model in 3D space.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has special find representation model
   * - Label (it)
     - Ha modello di rappresentazione di reperto
   * - Reverse
     - ``is_sf_representation_model_of``
   * - Source
     - :ref:`SpecialFindUnit <type-SpecialFindUnit>`
   * - Target
     - :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`
   * - CIDOC
     - ``P138i_has_representation``

Description
-----------

Connects special find units to their representation model in 3D space.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_representation_model_sf')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_representation_model_sf', target)    # the contract checks the pair

