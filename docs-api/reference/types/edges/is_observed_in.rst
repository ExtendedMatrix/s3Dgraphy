.. _edge-is_observed_in:

is_observed_in
==============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A stratigraphic unit, a special find or a documentary unit is KNOWN THROUGH a topographic unit (UT): the wall seen in a cellar, the mosaic in a test pit, the roof tiles picked up on the surface are observed in the UT that frames that observation.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is observed in
   * - Label (it)
     - È osservata in
   * - Reverse
     - ``observes``
   * - Source
     - :ref:`StratigraphicUnit <type-StratigraphicUnit>`, :ref:`SpecialFindUnit <type-SpecialFindUnit>`, :ref:`DocumentaryStratigraphicUnit <type-DocumentaryStratigraphicUnit>`
   * - Target
     - :ref:`TopographicUnitNode <type-TopographicUnitNode>`
   * - CIDOC
     - ``P46i_forms_part_of``

Description
-----------

A stratigraphic unit, a special find or a documentary unit is KNOWN THROUGH a topographic unit (UT): the wall seen in a cellar, the mosaic in a test pit, the roof tiles picked up on the surface are observed in the UT that frames that observation. The UT is the macro-set of what is seen there (E.D., 20 Nov 2026: «l'unità stratigrafica fa da contenuto di un macro insieme che è l'unità topografica»), and it contains its special finds. New in 1.6.56 (MICRO-LG2). Distinct from is\_part\_of, the PHYSICAL containment between units of the scale of contact, and from is\_in\_functional\_unit, which says what a set of units WAS: a functional unit (the domus) reads its units THROUGH the UT where they were seen (the wall of the cellar in UT 12, the mosaic in UT 15). The boundary between the two scales stays legible.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_observed_in')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_observed_in', target)    # the contract checks the pair

