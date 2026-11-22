.. _edge-survive_in_epoch:

survive_in_epoch
================

.. note::

   Generated from the datamodels (nodes 1.6.53, connections 1.6.58) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates that a node continues to exist in a given epoch.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Survives in epoch
   * - Label (it)
     - Sopravvive nell'epoca
   * - Reverse
     - ``contains_surviving``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`, :ref:`DocumentNode <type-DocumentNode>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Target
     - :ref:`EpochNode <type-EpochNode>`
   * - CIDOC
     - ``P132_spatiotemporally_overlaps_with · em:survivesInEpoch``

Description
-----------

Indicates that a node continues to exist in a given epoch.

From em
-------

.. code-block:: python

   em.graph.edges(type='survive_in_epoch')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'survive_in_epoch', target)    # the contract checks the pair

