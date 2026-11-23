.. _edge-has_first_epoch:

has_first_epoch
===============

.. note::

   Generated from the datamodels (nodes 1.6.55, connections 1.6.61) for em API 1.2.0 by ``docs-api/_tools/gen_types.py``.

*Indicates the initial epoch associated with a node.*

.. list-table::
   :widths: 25 75

   * - Label (en)
     - Has first epoch
   * - Label (it)
     - Ha come prima epoca
   * - Reverse
     - ``is_first_epoch_of``
   * - Source
     - :ref:`StratigraphicNode <type-StratigraphicNode>`, :ref:`RepresentationModelNode <type-RepresentationModelNode>`, :ref:`RepresentationModelDocNode <type-RepresentationModelDocNode>`, :ref:`RepresentationModelSpecialFindNode <type-RepresentationModelSpecialFindNode>`, :ref:`ParadataNodeGroup <type-ParadataNodeGroup>`, :ref:`ParadataNode <type-ParadataNode>`, :ref:`ActivityNodeGroup <type-ActivityNodeGroup>`, :ref:`FunctionalUnitNodeGroup <type-FunctionalUnitNodeGroup>`, :ref:`AuthorNode <type-AuthorNode>`, :ref:`LandscapeUnitNode <type-LandscapeUnitNode>`
   * - Target
     - :ref:`EpochNode <type-EpochNode>`
   * - CIDOC
     - ``P10_falls_within · em:firstAttestedInEpoch``

Description
-----------

Indicates the initial epoch associated with a node.

From em
-------

.. code-block:: python

   em.graph.edges(type='has_first_epoch')                  # read
   with em.write("Link") as tx:
       tx.add_edge(source, 'has_first_epoch', target)    # the contract checks the pair

