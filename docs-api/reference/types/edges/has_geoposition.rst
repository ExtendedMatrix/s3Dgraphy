.. _edge-has_geoposition:

has_geoposition
===============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents a connection with the geoposition node of a given node.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has geoposition
   * - Label (it)
     - Ha posizione geografica
   * - Reverse
     - ``is_geoposition_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`
   * - Target
     - :ref:`GeoPositionNode <type-GeoPositionNode>`
   * - CIDOC
     - ``P53_has_former_or_current_location``

Description
-----------

Represents a connection with the geoposition node of a given node.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_geoposition')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_geoposition', target)    # the contract checks the pair

