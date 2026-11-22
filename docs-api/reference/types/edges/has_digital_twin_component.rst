.. _edge-has_digital_twin_component:

has_digital_twin_component
==========================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Hierarchical containment between HDTs.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has digital twin component
   * - Label (it)
     - Ha componente del gemello digitale
   * - Reverse
     - ``is_digital_twin_component_of``
   * - Source
     - :ref:`HDTNode <type-HDTNode>`
   * - Target
     - :ref:`HDTNode <type-HDTNode>`
   * - CIDOC
     - ``hdto:HP3i_has_digital_twin_component``

Description
-----------

Hierarchical containment between HDTs. A parent HDT has component child-HDTs. HDT-O HP3 (inverse) per ECHOES D7.1 §4.2. Use case: Colosseo\_HDT\_overall has\_digital\_twin\_component Colosseo\_HDT\_Flavian / Colosseo\_HDT\_medieval\_fortress / Colosseo\_HDT\_christian\_site\_1800. Transitive: chains of containment are inferred.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_digital_twin_component')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_digital_twin_component', target)    # the contract checks the pair

