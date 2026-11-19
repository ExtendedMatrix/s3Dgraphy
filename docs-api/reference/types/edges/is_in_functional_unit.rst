.. _edge-is_in_functional_unit:

is_in_functional_unit
=====================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Membership of a stratigraphic unit in a FunctionalUnitNodeGroup (DP-72): the units that together make up one recognisable architectural component — the column made of its US.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in functional unit
   * - Label (it)
     - È nell'unità funzionale
   * - Reverse
     - ``includes_in_functional_unit``
   * - Source
     - :ref:`SpecialFindUnit <type-SpecialFindUnit>`, :ref:`VirtualSpecialFindUnit <type-VirtualSpecialFindUnit>`, :ref:`SeriesOfVirtualSpecialFindUnit <type-SeriesOfVirtualSpecialFindUnit>`, :ref:`ReusedSpecialFind <type-ReusedSpecialFind>`, :ref:`StratigraphicUnit <type-StratigraphicUnit>`, :ref:`DocumentaryStratigraphicUnit <type-DocumentaryStratigraphicUnit>`, :ref:`VirtualStratigraphicUnit <type-VirtualStratigraphicUnit>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - Target
     - :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`
   * - CIDOC
     - ``P46i_forms_part_of``

Description
-----------

Membership of a stratigraphic unit in a FunctionalUnitNodeGroup (DP-72): the units that together make up one recognisable architectural component — the column made of its US. A Functional Unit may itself be a member of another one (the capital inside the column). This is a TAG axis, not a nesting axis: membership is m:n and additive, it does NOT claim the member's primary drawing parent, and it does not constrain the member's epoch. That distinction is the whole reason this edge exists alongside is\_part\_of, which projects to the same CIDOC property: a Functional Unit legitimately spans epochs (a wall built across four of them still carries the roof as one body), and a swimlane box cannot — so the functional reading lives in its own view, beside pure stratigraphy, without either constraining the other. Orthogonal to is\_in\_activity (intention), is\_in\_location (place) and the epoch axis (time).

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_functional_unit')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_functional_unit', target)    # the contract checks the pair

