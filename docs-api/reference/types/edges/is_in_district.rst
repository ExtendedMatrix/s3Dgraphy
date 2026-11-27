.. _edge-is_in_district:

is_in_district
==============

.. note::

   Generated from the datamodels (nodes 1.6.57, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*A unit of the landscape (UT, UT0, another district) or a site (a LocationNodeGroup of level sito, virtual or not) belongs to a DISTRICT (DistrictNode, node datamodel 1.6.41).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Is in district
   * - Label (it)
     - È nel distretto
   * - Reverse
     - ``includes_in_district``
   * - Source
     - :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`
   * - Target
     - :ref:`DistrictNode <type-DistrictNode>`
   * - CIDOC
     - ``P53_has_former_or_current_location``

Description
-----------

A unit of the landscape (UT, UT0, another district) or a site (a LocationNodeGroup of level sito, virtual or not) belongs to a DISTRICT (DistrictNode, node datamodel 1.6.41). An interpretation of PERTINENCE, not a geometric fact: the villa is in its fundus because somebody argues it, not because two polygons overlap — the overlap is computed from the geometries, never written. Declared, so signed and argued by its paradata like any declaration. m:n: a unit may belong to several districts (the villa in its fundus and in the territory of the town); a district may be in another district (the Forum in Pompeii) with the same edge. The VALIDITY in time of a membership is DERIVED as the intersection of the two lives (as for a functional unit), computed by s3dgraphy.landscape, never written. New in 1.6.53 (MICRO-LANDSCAPE-ONTOLOGIA, D-LG6): is\_in\_location says WHAT NAMED PLACE a thing is in (an atemporal identity), is\_part\_of is physical containment, is\_in\_functional\_unit what a set of units IS; none says the pertinence of a site to a declared portion of territory that has a time of its own.

From em
-------

.. code-block:: python

   em.graph.edges(type='is_in_district')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'is_in_district', target)    # the contract checks the pair

