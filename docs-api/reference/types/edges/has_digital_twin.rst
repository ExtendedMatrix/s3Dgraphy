.. _edge-has_digital_twin:

has_digital_twin
================

.. note::

   Generated from the datamodels (nodes 1.6.51, connections 1.6.55) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Links a heritage entity to its Heritage Digital Twin (HDTNode), at ANY scale: a site, a building, a single unit (an inscription, US 100).*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has digital twin
   * - Label (it)
     - Ha gemello digitale
   * - Reverse
     - ``is_digital_twin_of``
   * - Source
     - :ref:`HeritageEntityNode <type-HeritageEntityNode>`, :ref:`StratigraphicNode <type-StratigraphicNode>`
   * - Target
     - :ref:`HDTNode <type-HDTNode>`
   * - CIDOC
     - ``hdto:HP1_has_digital_twin``

Description
-----------

Links a heritage entity to its Heritage Digital Twin (HDTNode), at ANY scale: a site, a building, a single unit (an inscription, US 100). HDT-O HP1 per ECHOES D7.1 §4.2. Two uses, told apart by the twin and not by the edge. (1) The STUDY's twin: from the HC1 the study is about (study\_about\_heritage) to the HDTNode marked data.hdto\_role = 'twin' — one per graph, the chain EMStudio's applyHdto and s3dgraphy.hdto.declare\_hdto write (HC1 -HP1-> HC2 -HP33-> HC16). (2) The twin of a PART (1.6.42): from a stratigraphic unit or an HC1 inside the graph to an HDTNode WITHOUT hdto\_role — read as a list by s3dgraphy.hdto.read\_part\_twins (read\_hdto()['parts']), each with the unit or entity it belongs to. No hierarchy is presumed: which part belongs to which whole is said by heritage\_part\_of (HC1 to HC1) and is\_part\_of (unit to unit), never inferred from the twins; HDT to HDT nesting is has\_digital\_twin\_component. In RDF the edge is hdto:HP1\_has\_digital\_twin whatever the source; its rdfs:domain (HC1) makes a unit with a twin a heritage entity as well, which is what having a twin means.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_digital_twin')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_digital_twin', target)    # the contract checks the pair

