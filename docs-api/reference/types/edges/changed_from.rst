.. _edge-changed_from:

changed_from
============

.. note::

   Generated from the datamodels (nodes 1.6.54, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Represents an object that changes over time.*

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

Represents an object that changes over time. Between two STRATIGRAPHIC units (the dotted line of the GraphML) it says a change of POSITION IN SPACE (E.D., 22 Nov 2026): the matter moved — the capital of the colonnade walled up as an RSF in a channel, the block dismantled and rebuilt, the anastylosis. It runs from the unit in the ORIGINAL position (often a USV/s or a USD, because that position is reconstructed) to the unit in the NEW one, by convention US and US-b: the INSTANCE CHAIN of one object across its positions — the same capital as an SF found today, as the USD of its collapse, as a US — or a VSF — in its Roman place. Each instance is a unit with what a unit has: its epochs, its representation models with their own transform (the position for that epoch), its conservation\_state property. The proxy's geometry is ONE (the geometry property of one instance), the placement is per instance. An earlier instance is an SF only when the piece is estimated equal to the ancient one; otherwise it is a VSF. A CHANGE OF FUNCTION WITHOUT DISPLACEMENT is not a changed\_from: the same unit, in the same place, is a member (is\_in\_functional\_unit) of several functional units — the wall of the villa, then of the castle — and each membership is an INSTANCE whose interval is computed (s3dgraphy.functional\_units.instances). A unit that merely survives is one node, alive until today unless an action takes it away, not a chain. Between two FunctionalUnitNodeGroup it is the chain of identities (change\_type transformation). Read by s3dgraphy.spatiotemporal.epoch\_instances (connections 1.6.46); the graphs drawn before 1.6.57 are reviewed by s3dgraphy.functional\_units.changed\_from\_to\_review.

From em
-------

.. code-block:: python

   em.graph.edges(type='changed_from')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'changed_from', target)    # the contract checks the pair

