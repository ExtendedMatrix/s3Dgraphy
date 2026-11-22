.. _edge-has_property:

has_property
============

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.59) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Connects a node to one of its properties.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has property
   * - Label (it)
     - Ha la proprietà
   * - Reverse
     - ``is_property_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`EpochNode <type-EpochNode>`, :ref:`GraphNode <type-GraphNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LocationNodeGroup <type-LocationNodeGroup>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`, :ref:`ActivityNodeGroup <type-ActivityNodeGroup>`, :ref:`TimeBranchNodeGroup <type-TimeBranchNodeGroup>`
   * - Target
     - :ref:`PropertyNode <type-PropertyNode>`
   * - CIDOC
     - ``P43_has_dimension · em:hasQualia``

Description
-----------

Connects a node to one of its properties.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_property')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_property', target)    # the contract checks the pair

