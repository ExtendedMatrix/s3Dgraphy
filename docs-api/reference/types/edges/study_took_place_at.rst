.. _edge-study_took_place_at:

study_took_place_at
===================

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links an HC9 Study to the topographic place where it was carried out — the LocationNodeGroup of the site, the last link of the toponym chain (nation → region → province → comune → site), or of a saggio in the site (kind study, is\_in\_location the site: E.D., 11 Oct 2026), so the site finds the study going up.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Study took place at
   * - Label (it)
     - Lo studio si è svolto in
   * - Reverse
     - ``was_place_of_study``
   * - Source
     - :ref:`StudyNode <type-StudyNode>`
   * - Target
     - :ref:`LocationNodeGroup <type-LocationNodeGroup>`
   * - CIDOC
     - ``P7_took_place_at``

Description
-----------

Links an HC9 Study to the topographic place where it was carried out — the LocationNodeGroup of the site, the last link of the toponym chain (nation → region → province → comune → site), or of a saggio in the site (kind study, is\_in\_location the site: E.D., 11 Oct 2026), so the site finds the study going up. E.D., 10 Oct 2026: a stratigraphic trench is a study, the site is topography, and studies always hang off the place, off an HC1 only when the heritage is recognised.

From em
-------

.. code-block:: python

   em.graph.edges(type='study_took_place_at')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'study_took_place_at', target)    # the contract checks the pair

