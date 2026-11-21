.. _edge-changed_from:

changed_from
============

.. note::

   Generated from the datamodels (nodes 1.6.52, connections 1.6.56) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents an object that changes over time, indicating temporal transformation.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Changed from
   * - Label (it)
     - Trasformato da
   * - Reverse
     - ``changed_to``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - CIDOC
     - ``P123i_resulted_from · AP4_produced_surface (was_surface_produced_by)``

Description
-----------

Represents an object that changes over time, indicating temporal transformation. It is the INSTANCE CHAIN of one object across the epochs (the dotted line of the GraphML): the same capital as an SF found today, as the USD of its collapse, as a US — or a VSF — in its Roman place; one unit per epoch, linked by changed\_from. Each instance is a unit with what a unit has: its epochs, its representation models with their own transform (the position for that epoch), its conservation\_state property. The proxy's geometry is ONE (the geometry property of one instance), the placement is per instance. An earlier instance is an SF only when the piece is estimated equal to the ancient one; otherwise it is a VSF. A unit that merely survives unchanged is one node with survive\_in\_epoch, not a chain. Read by s3dgraphy.spatiotemporal.epoch\_instances (connections 1.6.46).

From em
-------

.. code-block:: python

   em.graph.edges(type='changed_from')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'changed_from', target)    # the contract checks the pair

