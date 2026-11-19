.. _edge-has_digital_object_part:

has_digital_object_part
=======================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HDT (or any HC14 Volatile Digital Object) to an auxiliary digital object that is NOT a proposition set — e.g., a 3D survey database, a point cloud, a generic linked resource.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has digital object part
   * - Label (it)
     - Ha parte di oggetto digitale
   * - Reverse
     - ``is_digital_object_part_of``
   * - Source
     - :ref:`HDTNode <type-HDTNode>`
   * - Target
     - :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`ResourceNode <type-ResourceNode>`
   * - CIDOC
     - ``hdto:HP29_has_digital_object_part · P106_is_composed_of``

Description
-----------

Links an HDT (or any HC14 Volatile Digital Object) to an auxiliary digital object that is NOT a proposition set — e.g., a 3D survey database, a point cloud, a generic linked resource. HDT-O HP29 per ECHOES D7.1 §4.2.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_digital_object_part')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_digital_object_part', target)    # the contract checks the pair

