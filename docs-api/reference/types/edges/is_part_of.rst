.. _edge-is_part_of:

is_part_of
==========

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Mereological (part–whole) PHYSICAL containment, not chronological or stratigraphic: a Special Find reused inside a wall, tile fragments inside a reconstructed roof (DP-36).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is part of
   * - Label (it)
     - Fa parte di
   * - Reverse
     - ``has_part``
   * - Source
     - :ref:`SpecialFindUnit <type-SpecialFindUnit>`, :ref:`VirtualSpecialFindUnit <type-VirtualSpecialFindUnit>`, :ref:`SeriesOfVirtualSpecialFindUnit <type-SeriesOfVirtualSpecialFindUnit>`, :ref:`ReusedSpecialFind <type-ReusedSpecialFind>`, :ref:`StratigraphicUnit <type-StratigraphicUnit>`, :ref:`DocumentaryStratigraphicUnit <type-DocumentaryStratigraphicUnit>`, :ref:`VirtualStratigraphicUnit <type-VirtualStratigraphicUnit>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`StratigraphicUnit <type-StratigraphicUnit>`, :ref:`DocumentaryStratigraphicUnit <type-DocumentaryStratigraphicUnit>`, :ref:`VirtualSpecialFindUnit <type-VirtualSpecialFindUnit>`, :ref:`SeriesOfVirtualSpecialFindUnit <type-SeriesOfVirtualSpecialFindUnit>`
   * - CIDOC
     - ``P46i_forms_part_of · AP21i_is_contained_in``

Description
-----------

Mereological (part–whole) PHYSICAL containment, not chronological or stratigraphic: a Special Find reused inside a wall, tile fragments inside a reconstructed roof (DP-36). Containment is a relationship, not a change in node type: a US that contains elements is still a US, and the presence of is\_part\_of edges is the only discriminant that identifies it as a container. This is the NESTING axis — one primary parent, drawn as a box around its members — so a FunctionalUnitNodeGroup is NOT a target here (its membership is the m:n tag axis is\_in\_functional\_unit, DP-72). A Functional Unit may however be a SOURCE: a whole component physically embedded in a stratigraphic unit (a column engaged in a later wall).

From em
-------

.. code-block:: python

   em.graph.edges(type='is_part_of')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_part_of', target)    # the contract checks the pair

